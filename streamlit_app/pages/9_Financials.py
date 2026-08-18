from datetime import datetime

import pandas as pd
import streamlit as st

import api
from constants import ACTIVE_STATUSES, COLLECTION_TIERS, STATUS_LABELS


def _tier(collection) -> str:
    return COLLECTION_TIERS.get(str(collection or "").strip().lower(), "Unclassified")

st.set_page_config(page_title="Financials", layout="wide", page_icon="⌚")
st.title("Financials")
st.caption("Capital deployed, realized P&L, and style performance — pulled straight from your inventory data.")


@st.cache_data(ttl=120)
def _load():
    return api.export_watches()


try:
    records = _load()
except Exception as e:
    st.error(f"Failed to load data: {e}")
    st.stop()

df = pd.DataFrame(records)
if df.empty:
    st.info("No watches yet.")
    st.stop()

biz = df[df.get("is_personal", False) != True].copy()

NUMERIC_COLS = [
    "total_landed_cost_usd", "sale_price_usd", "net_profit_usd",
    "shipping_cost_usd", "platform_fees_usd", "total_additional_costs_usd",
    "total_labor_hours",
]
for col in NUMERIC_COLS:
    if col in biz.columns:
        biz[col] = pd.to_numeric(biz[col], errors="coerce")

# ── Section 1: Capital Deployed ────────────────────────────────────────────────
st.header("Capital Deployed")

active = biz[biz["current_status"].isin(ACTIVE_STATUSES)]

c1, c2, c3 = st.columns(3)
c1.metric("Pieces in inventory", len(active))
c2.metric("Capital tied up", f"${active['total_landed_cost_usd'].sum():,.2f}")
c3.metric(
    "Avg cost / piece",
    f"${active['total_landed_cost_usd'].mean():,.2f}" if len(active) else "$0.00",
)

if not active.empty:
    by_status = (
        active.groupby("current_status")
        .agg(Pieces=("watch_id", "count"), Capital=("total_landed_cost_usd", "sum"))
        .reset_index()
    )
    by_status["Status"] = by_status["current_status"].map(STATUS_LABELS).fillna(by_status["current_status"])
    by_status = by_status.sort_values("Capital", ascending=False)
    st.dataframe(
        by_status[["Status", "Pieces", "Capital"]].rename(columns={"Capital": "Capital ($)"}),
        width="stretch",
        hide_index=True,
    )

    active = active.copy()
    active["days_in_system"] = (
        pd.Timestamp.now(tz="UTC") - pd.to_datetime(active["created_at"], utc=True, errors="coerce")
    ).dt.days
    aging = active.sort_values("days_in_system", ascending=False).head(5)
    if not aging.empty:
        st.caption("Oldest pieces still in inventory")
        st.dataframe(
            aging[["reference", "brand", "collection", "current_status", "days_in_system", "total_landed_cost_usd"]]
            .rename(columns={
                "current_status": "Status",
                "days_in_system": "Days",
                "total_landed_cost_usd": "Landed ($)",
            }),
            width="stretch",
            hide_index=True,
        )

st.divider()

# ── Section 2: Realized P&L ────────────────────────────────────────────────────
st.header("Realized P&L")

sold = biz[biz["sale_price_usd"].notna()].copy()

if sold.empty:
    st.info("No closed sales yet.")
else:
    revenue = sold["sale_price_usd"].sum()
    profit = sold["net_profit_usd"].sum()
    margin = (profit / revenue * 100) if revenue else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Pieces sold", len(sold))
    c2.metric("Revenue", f"${revenue:,.2f}")
    c3.metric("Profit", f"${profit:,.2f}")
    c4.metric("Margin", f"{margin:.1f}%")

    sold["sale_month"] = pd.to_datetime(sold["sale_date"], errors="coerce").dt.to_period("M").astype(str)
    monthly = (
        sold.groupby("sale_month")
        .agg(Revenue=("sale_price_usd", "sum"), Profit=("net_profit_usd", "sum"))
        .reset_index()
        .sort_values("sale_month")
    )
    st.bar_chart(monthly.set_index("sale_month")[["Revenue", "Profit"]])

    with st.expander("All closed sales"):
        cols = ["reference", "brand", "collection", "sale_date", "sale_platform", "sale_price_usd", "net_profit_usd"]
        cols = [c for c in cols if c in sold.columns]
        st.dataframe(
            sold[cols].sort_values("sale_date", ascending=False).rename(columns={
                "sale_price_usd": "Sale ($)",
                "net_profit_usd": "Profit ($)",
            }),
            width="stretch",
            hide_index=True,
        )

st.divider()

# ── Section 3: Style Performance ───────────────────────────────────────────────
st.header("Style Performance")

if sold.empty:
    st.info("No closed sales yet to rank.")
else:
    sold["tier"] = sold["collection"].apply(_tier)

    group_choice = st.selectbox(
        "Group by", ["Tier", "Movement Type", "Case Material", "Collection", "Reference"],
    )
    group_col = {
        "Tier": "tier",
        "Collection": "collection",
        "Case Material": "case_material",
        "Movement Type": "movement_type",
        "Reference": "reference",
    }[group_choice]

    sold["days_to_sell"] = (
        pd.to_datetime(sold["sale_date"], utc=True, errors="coerce")
        - pd.to_datetime(sold["created_at"], utc=True, errors="coerce")
    ).dt.days

    # Some older records never had every field written to DynamoDB at all (e.g.
    # movement_type), which becomes NaN once loaded into a DataFrame — and pandas'
    # groupby() silently drops NaN keys by default, making those sold pieces vanish
    # from this table even though they're counted in the totals above. Bucket
    # missing/blank values explicitly instead of letting them disappear.
    group_key = sold[group_col].astype(str).str.strip()
    group_key = group_key.fillna("(Unspecified)")
    group_key = group_key.mask(group_key.isin(["", "nan", "None"]), "(Unspecified)")
    sold["_group_key"] = group_key

    perf = (
        sold.groupby("_group_key", dropna=False)
        .agg(
            Sold=("watch_id", "count"),
            Total_Profit=("net_profit_usd", "sum"),
            Avg_Profit=("net_profit_usd", "mean"),
            Avg_Days_to_Sell=("days_to_sell", "mean"),
        )
        .reset_index()
        .sort_values("Total_Profit", ascending=False)
    )
    perf["Total_Profit"] = perf["Total_Profit"].round(2)
    perf["Avg_Profit"] = perf["Avg_Profit"].round(2)
    perf["Avg_Days_to_Sell"] = perf["Avg_Days_to_Sell"].round(0)

    st.dataframe(
        perf.rename(columns={
            "_group_key": group_choice,
            "Total_Profit": "Total Profit ($)",
            "Avg_Profit": "Avg Profit ($)",
            "Avg_Days_to_Sell": "Avg Days to Sell",
        }),
        width="stretch",
        hide_index=True,
    )

st.divider()

# ── Section 4: Ask Your Data ───────────────────────────────────────────────────
st.header("Ask Your Data")
st.caption("Free-form questions answered from your actual inventory + sales data — not a canned report.")

EXAMPLE_PROMPTS = [
    "Which collection is most profitable per piece, not just in total?",
    "How has my average margin trended month over month?",
    "Which pieces have been sitting the longest and what's tied up in them?",
]
if "financials_question" not in st.session_state:
    st.session_state.financials_question = ""

ex_cols = st.columns(len(EXAMPLE_PROMPTS))
for col, ex in zip(ex_cols, EXAMPLE_PROMPTS):
    if col.button(ex, width="stretch"):
        st.session_state.financials_question = ex

question = st.text_area("Your question", key="financials_question", height=80)

if st.button("Analyze", type="primary", disabled=not question.strip()):
    with st.spinner("Analyzing…"):
        ai_cols = [c for c in [
            "watch_id", "brand", "collection", "reference", "jdm_model", "case_material", "movement_type",
            "current_status", "created_at", "total_landed_cost_usd", "total_labor_hours",
            "sale_price_usd", "sale_platform", "sale_date", "shipping_cost_usd", "platform_fees_usd",
            "net_profit_usd",
        ] if c in biz.columns]
        data_csv = biz[ai_cols].to_csv(index=False)

        import anthropic
        client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])

        prompt = f"""You are a data analyst for a JDM watch reselling side business. Below is the full \
inventory + sales dataset as CSV (one row per watch; sale_* fields are blank if the watch hasn't sold yet).

Today's date: {datetime.now().strftime('%Y-%m-%d')}

CSV:
{data_csv}

Answer the question using only the data above. Show your work with real numbers (counts, sums, averages) \
pulled from the data — don't hand-wave. Keep it concise and skimmable; use a short markdown table if it \
helps. If the data can't answer the question, say so plainly rather than guessing.

Question: {question}"""

        resp = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        answer = resp.content[0].text

    st.markdown(answer)
