import pandas as pd
import streamlit as st
from datetime import date as date_type

import api
from constants import AD_CAMPAIGN_PLATFORMS, AD_CAMPAIGN_PLATFORM_LABELS

st.set_page_config(page_title="Ad Campaigns", layout="wide", page_icon="⌚")
st.title("Ad Campaigns")
st.caption(
    "Record ad spend that covers multiple pieces at once (eBay Offsite Ads, Reddit "
    "promotion) and split it evenly across the watches it applied to — instead of "
    "hand-splitting one advertising cost into several manual entries."
)


@st.cache_data(ttl=60)
def _load_watches():
    return api.list_watches()


try:
    all_watches = _load_watches()
except Exception as e:
    st.error(f"Failed to load watches: {e}")
    st.stop()

eligible = [w for w in all_watches if not w.get("is_personal")]

if not eligible:
    st.info("No eligible business watches.")
    st.stop()

watch_opts = {
    w["watch_id"]: f"[{w['watch_id']}] {w.get('brand', '')} {w.get('collection', '')} "
                    f"{w.get('reference', '')}"
    for w in eligible
}

selected_ids = st.multiselect(
    "Watches this campaign covered",
    list(watch_opts.keys()),
    format_func=lambda wid: watch_opts[wid],
)

c1, c2, c3 = st.columns(3)
platform = c1.selectbox(
    "Platform", AD_CAMPAIGN_PLATFORMS,
    format_func=lambda p: AD_CAMPAIGN_PLATFORM_LABELS.get(p, p),
)
total_cost = c2.number_input("Total cost (USD)", min_value=0.01, step=1.0, format="%.2f")
campaign_date = c3.date_input("Campaign date", value=date_type.today())

notes = st.text_input("Notes", placeholder="e.g. eBay Offsite Ads, July invoice")

if selected_ids and total_cost:
    per_watch = round(total_cost / len(selected_ids), 2)
    st.caption(f"**{len(selected_ids)}** watches selected → **${per_watch:,.2f}** each (even split).")

if st.button(
    "Create & Allocate", type="primary",
    disabled=not (selected_ids and total_cost),
):
    try:
        with st.spinner("Creating campaign…"):
            result = api.create_campaign({
                "platform": platform,
                "total_cost_usd": total_cost,
                "campaign_date": str(campaign_date),
                "notes": notes,
                "watch_ids": selected_ids,
            })
            campaign_id = result["campaign_id"]
        with st.spinner("Allocating…"):
            alloc_result = api.allocate_campaign(campaign_id)
        st.cache_data.clear()
        st.success(
            f"Campaign `{campaign_id}` created — "
            f"${alloc_result['per_watch_usd']:,.2f} added as an advertising cost to "
            f"{alloc_result['watches']} watch(es)."
        )
        if alloc_result.get("allocations"):
            alloc_df = pd.DataFrame(alloc_result["allocations"]).rename(
                columns={"watch_id": "Watch ID", "allocated_usd": "Allocated ($)"}
            )
            st.dataframe(alloc_df, hide_index=True, width="stretch")
    except Exception as e:
        st.error(f"Failed: {e}")
