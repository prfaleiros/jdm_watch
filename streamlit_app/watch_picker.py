"""Shared clickable watch list — replaces every per-page "pick a watch" dropdown.

With 50-60+ watches a dropdown is unusable; a filterable table is. Every page that needs a
watch (or several) goes through `watch_picker`, so the list looks and behaves the same
everywhere: search box, status filter, thumbnail, and row selection that returns the id(s).
"""
import pandas as pd
import streamlit as st

from constants import VALID_STATUSES, STATUS_LABELS, STATUS_ORDER


def reset_picker(key: str) -> None:
    """Clear the picker's row selection. Streamlit keeps a dataframe's selection under its
    widget key, so after acting on a pick (e.g. "← Back to list") the old row would be
    re-selected on the next render; bumping the generation gives the widget a fresh key."""
    st.session_state[f"{key}__gen"] = st.session_state.get(f"{key}__gen", 0) + 1


def _is_url(x) -> bool:
    return isinstance(x, str) and x.startswith("http")


def watch_picker(
    watches: list,
    key: str,
    *,
    multi: bool = False,
    default_statuses: list = None,
    status_filter: bool = True,
    empty_msg: str = "No watches match.",
) -> list:
    """Render a filterable, selectable watch table and return the selected watch_id(s).

    multi=False → click one row (returns [id] or []); multi=True → tick any number of rows.
    `default_statuses` pre-sets the status filter (None = all statuses).
    """
    if not watches:
        st.info(empty_msg)
        return []

    df = pd.DataFrame(watches)
    for col in ("brand", "collection", "reference", "jdm_model", "current_status"):
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("")
    if "is_personal" not in df.columns:
        df["is_personal"] = False
    df["is_personal"] = df["is_personal"].fillna(False).astype(bool)

    # Cost shown = true all-in basis, falling back to bare landed for pre-split records.
    zero = pd.Series(0.0, index=df.index)
    cost = pd.to_numeric(df.get("total_cost_basis_usd", zero), errors="coerce")
    landed = pd.to_numeric(df.get("total_landed_cost_usd", zero), errors="coerce")
    df["cost"] = cost.fillna(landed).fillna(0)

    # ── Filters ──────────────────────────────────────────────────────────────
    present = [s for s in VALID_STATUSES if s in set(df["current_status"])]
    fc1, fc2 = st.columns([2, 3]) if status_filter else (None, st.container())
    query = fc2.text_input(
        "Search", key=f"{key}__q", placeholder="Search brand, collection, reference, ID…",
        label_visibility="collapsed",
    )
    if status_filter:
        default = [s for s in (default_statuses or present) if s in present]
        chosen = fc1.multiselect(
            "Status", present, default=default, key=f"{key}__status",
            format_func=lambda s: STATUS_LABELS.get(s, s), label_visibility="collapsed",
            placeholder="Status filter",
        )
        df = df[df["current_status"].isin(chosen)]
    q = (query or "").strip().lower()
    if q:
        hay = (df["watch_id"].astype(str) + " " + df["brand"] + " " + df["collection"] + " "
               + df["reference"] + " " + df["jdm_model"]).str.lower()
        df = df[hay.str.contains(q, regex=False)]

    if df.empty:
        st.info(empty_msg)
        return []

    df = df.assign(_order=df["current_status"].map(STATUS_ORDER).fillna(99)) \
           .sort_values(["_order", "watch_id"]).reset_index(drop=True)

    display = pd.DataFrame({
        "ID": df["watch_id"],
        "Watch": (df["brand"] + " " + df["collection"]).str.strip(),
        "Reference": df["reference"],
        "Model": df["jdm_model"],
        "Status": df["current_status"].map(lambda s: STATUS_LABELS.get(s, s)),
        "Cost ($)": df["cost"],
        "P": df["is_personal"].map(lambda x: "🔒" if x else ""),
    })
    col_config = {
        "Cost ($)": st.column_config.NumberColumn("Cost ($)", format="%.2f"),
        "P": st.column_config.TextColumn("", width="small"),
    }
    if "thumbnail_url" in df.columns and df["thumbnail_url"].apply(_is_url).any():
        display.insert(0, "Photo", df["thumbnail_url"].map(lambda x: x if _is_url(x) else ""))
        col_config["Photo"] = st.column_config.ImageColumn("Photo", width="small")

    st.caption(
        f"{len(df)} watch(es) — "
        + ("tick rows to select." if multi else "click a row's checkbox (left edge) to open it.")
    )
    event = st.dataframe(
        display,
        column_config=col_config,
        hide_index=True,
        width="stretch",
        on_select="rerun",
        selection_mode="multi-row" if multi else "single-row",
        key=f"{key}__df{st.session_state.get(f'{key}__gen', 0)}",
    )
    rows = event.selection.rows if event and event.selection else []
    return [str(df.iloc[i]["watch_id"]) for i in rows if i < len(df)]
