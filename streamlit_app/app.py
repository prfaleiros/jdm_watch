import streamlit as st
import pandas as pd
from datetime import date as date_type
import api
from constants import VALID_STATUSES, STATUS_LABELS, STATUS_ORDER, ACTIVE_STATUSES

st.set_page_config(page_title="JDM Watch Business", layout="wide", page_icon="⌚")
st.title("Inventory")

@st.cache_data(ttl=30)
def load_watches():
    return api.list_watches()

col_refresh, col_export = st.columns([1, 5])
if col_refresh.button("Refresh"):
    st.cache_data.clear()

if col_export.button("Export full CSV 📥"):
    with st.spinner("Fetching full records…"):
        try:
            full_data = api.export_watches()
            export_df = pd.DataFrame(full_data).drop(
                columns=["thumbnail_url", "thumbnail_key"], errors="ignore"
            )
            csv_bytes = export_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "Download watches.csv",
                csv_bytes,
                file_name="watches.csv",
                mime="text/csv",
                key="csv_dl",
            )
        except Exception as e:
            st.error(f"Export failed: {e}")

try:
    watches = load_watches()
except Exception as e:
    st.error(f"API error: {e}")
    st.stop()

if not watches:
    st.info("No watches yet. Add one from New Watch.")
    st.stop()

df = pd.DataFrame(watches)
df["is_personal"] = df["is_personal"].fillna(False)
df["total_landed_cost_usd"] = pd.to_numeric(df["total_landed_cost_usd"], errors="coerce").fillna(0)
# "Landed" in this grid means true all-in cost (acquisition + pre-sale bench costs) — falls
# back to pure landed for watches predating the cost-basis split (see costs.py).
if "total_cost_basis_usd" in df.columns:
    df["total_landed_cost_usd"] = pd.to_numeric(
        df["total_cost_basis_usd"], errors="coerce"
    ).fillna(df["total_landed_cost_usd"])
df["status_order"] = df["current_status"].map(STATUS_ORDER).fillna(99)

# --- Stats ---
business = df[~df["is_personal"]]
active_business = business[business["current_status"].isin(ACTIVE_STATUSES)]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Pieces", len(df))
c2.metric("Active (Business)", len(active_business))
c3.metric("Landed Value", f"${active_business['total_landed_cost_usd'].sum():,.2f}")
c4.metric("On Bench", len(df[df["current_status"] == "on_bench"]))

st.divider()

# --- Filters ---
fc1, fc2, fc3 = st.columns([3, 2, 1])
selected_statuses = fc1.multiselect(
    "Status filter",
    VALID_STATUSES,
    default=ACTIVE_STATUSES,
    format_func=lambda s: STATUS_LABELS.get(s, s),
)
show_personal = fc3.checkbox("Show personal", value=True)

filtered = df[df["current_status"].isin(selected_statuses)]
if not show_personal:
    filtered = filtered[~filtered["is_personal"]]

filtered = filtered.sort_values("status_order")

# --- Table ---
if filtered.empty:
    st.info("No watches match the current filters.")
else:
    display = filtered.copy()
    display["Watch"] = display["brand"].fillna("") + " " + display["collection"].fillna("")
    display["Status"] = display["current_status"].map(STATUS_LABELS)
    display["P"] = display["is_personal"].apply(lambda x: "🔒" if x else "")
    # total_landed_cost_usd stays numeric — NumberColumn handles display & keeps sort correct

    def _is_url(x):
        return isinstance(x, str) and x.startswith("http")

    has_thumbnails = (
        "thumbnail_url" in display.columns
        and display["thumbnail_url"].apply(_is_url).any()
    )

    # Base column set — numeric landed for correct sort
    base_cols = ["watch_id", "Watch", "reference", "jdm_model", "Status", "total_landed_cost_usd", "P"]
    col_config = {
        "watch_id":              st.column_config.TextColumn("ID"),
        "Watch":                 st.column_config.TextColumn("Watch"),
        "reference":             st.column_config.TextColumn("Reference"),
        "jdm_model":             st.column_config.TextColumn("Model"),
        "Status":                st.column_config.TextColumn("Status"),
        "total_landed_cost_usd": st.column_config.NumberColumn("Landed ($)", format="%.2f"),
        "P":                     st.column_config.TextColumn("", width="small"),
    }

    if has_thumbnails:
        # Non-URL values (None, NaN) → "" so ImageColumn shows blank, not "None" text
        display["Photo"] = display["thumbnail_url"].fillna("").apply(
            lambda x: x if _is_url(x) else ""
        )
        show_cols = ["Photo"] + base_cols
        col_config["Photo"] = st.column_config.ImageColumn("Photo", width="small")
    else:
        show_cols = base_cols

    st.dataframe(
        display[show_cols],
        column_config=col_config,
        width='stretch',
        hide_index=True,
    )

    # --- Navigate to watch ---
    st.divider()
    label_to_id = {
        f"[{row['watch_id']}] {row['brand']} {row['collection']} {row['reference']} · {STATUS_LABELS.get(row['current_status'], row['current_status'])}": row["watch_id"]
        for _, row in filtered.iterrows()
    }
    chosen = st.selectbox("Open watch", list(label_to_id.keys()), label_visibility="collapsed")
    if st.button("Open →", type="primary"):
        st.session_state["selected_watch_id"] = label_to_id[chosen]
        st.switch_page("pages/2_Watch.py")

    # --- Batch status update ---
    st.divider()
    with st.expander("⚡ Batch status update", expanded=False):
        st.caption(
            "Move a group of watches to a new status in one step — useful when a shipment arrives "
            "or a batch clears customs. Logs a transition entry on every selected watch."
        )
        watch_opts = {
            f"[{row['watch_id']}] {row['brand']} {row['collection']} {row['reference']}": row["watch_id"]
            for _, row in filtered.iterrows()
        }
        batch_sel = st.multiselect(
            "Watches to update", list(watch_opts.keys()),
            default=list(watch_opts.keys()),
            key="batch_sel",
        )
        bc1, bc2 = st.columns(2)
        batch_status = bc1.selectbox(
            "New status", VALID_STATUSES,
            format_func=lambda s: STATUS_LABELS.get(s, s),
            key="batch_status",
        )
        batch_date = bc2.date_input("Date", value=date_type.today(), key="batch_date")
        batch_notes = st.text_input(
            "Notes (applied to all)", placeholder="Arrived via DHL shipment…",
            key="batch_notes",
        )

        if st.button(
            f"Apply to {len(batch_sel)} watch(es) →",
            type="primary",
            disabled=not batch_sel,
            key="batch_apply",
        ):
            prog = st.progress(0, text="Updating…")
            errors = []
            for i, label in enumerate(batch_sel):
                wid = watch_opts[label]
                try:
                    api.add_transition(wid, batch_status, 0, batch_notes, str(batch_date))
                except Exception as e:
                    errors.append(f"{label}: {e}")
                prog.progress((i + 1) / len(batch_sel), text=f"Updated {i + 1}/{len(batch_sel)}…")
            prog.empty()
            st.cache_data.clear()
            if errors:
                for err in errors:
                    st.error(err)
            else:
                st.success(f"✓ {len(batch_sel)} watch(es) → **{STATUS_LABELS[batch_status]}**")
                st.rerun()
