import streamlit as st
import pandas as pd
from datetime import date as date_type
import api
from constants import VALID_STATUSES, STATUS_LABELS, STATUS_ORDER, ACTIVE_STATUSES
from watch_picker import watch_picker, reset_picker

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

# --- Watch list: click a row to open it ---
st.caption("Open a watch")
show_personal = st.checkbox("Show personal", value=True)
visible = [w for w in watches if show_personal or not w.get("is_personal")]

opened = watch_picker(
    visible, key="inv", default_statuses=ACTIVE_STATUSES,
    empty_msg="No watches match the current filters.",
)
if opened:
    st.session_state["selected_watch_id"] = opened[0]
    st.switch_page("pages/2_Watch.py")

# --- Batch status update ---
st.divider()
with st.expander("⚡ Batch status update", expanded=False):
    st.caption(
        "Move a group of watches to a new status in one step — useful when a shipment arrives "
        "or a batch clears customs. Logs a transition entry on every selected watch."
    )
    batch_ids = watch_picker(
        visible, key="batch", multi=True, default_statuses=ACTIVE_STATUSES,
        empty_msg="No watches match the current filters.",
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
        f"Apply to {len(batch_ids)} watch(es) →",
        type="primary",
        disabled=not batch_ids,
        key="batch_apply",
    ):
        prog = st.progress(0, text="Updating…")
        errors = []
        for i, wid in enumerate(batch_ids):
            try:
                api.add_transition(wid, batch_status, 0, batch_notes, str(batch_date))
            except Exception as e:
                errors.append(f"{wid}: {e}")
            prog.progress((i + 1) / len(batch_ids), text=f"Updated {i + 1}/{len(batch_ids)}…")
        prog.empty()
        st.cache_data.clear()
        reset_picker("batch")
        if errors:
            for err in errors:
                st.error(err)
        else:
            st.success(f"✓ {len(batch_ids)} watch(es) → **{STATUS_LABELS[batch_status]}**")
            st.rerun()
