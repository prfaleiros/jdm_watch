import streamlit as st
import pandas as pd
import api

st.set_page_config(page_title="Bid Calculator", layout="wide", page_icon="⌚")
st.title("Bid Calculator")
st.caption(
    "Enter what you expect to sell the watch for and the shipping context. "
    "The calculator tells you the maximum you should bid at auction in JPY to hit each profit tier."
)

with st.form("bid_calc"):
    st.subheader("Expected Sale")
    bc1, bc2 = st.columns(2)
    expected_sale = bc1.number_input(
        "Expected sale price (USD) *",
        min_value=1.0, step=5.0, format="%.2f",
        help="What do you realistically think this will sell for on eBay? Use a comparable listing as reference.",
    )
    fx_rate = bc2.number_input(
        "JPY / USD rate *",
        min_value=1.0, value=150.0, step=1.0, format="%.1f",
        help="Current exchange rate. Check Google: '1 USD to JPY'.",
    )

    st.subheader("Estimated Costs on This Watch")
    bc3, bc4, bc5 = st.columns(3)
    labor_hours = bc3.number_input(
        "Estimated bench hours",
        min_value=0.0, value=0.5, step=0.25, format="%.2f",
        help="Include inspection, cleaning, testing, photography, listing.",
    )
    repair_estimate = bc4.number_input(
        "Repair / parts estimate (USD)",
        min_value=0.0, step=1.0, format="%.2f",
        help="Crystal, strap, battery, capacitor, etc.",
    )
    pieces_in_shipment = bc5.number_input(
        "Watches in shipment",
        min_value=1, value=5, step=1,
        help="How many business watches share the shipping cost? Used to allocate international freight.",
    )

    submitted = st.form_submit_button("Calculate Max Bid", type="primary")

if submitted:
    payload = {
        "expected_sale_usd": expected_sale,
        "fx_rate": fx_rate,
        "labor_hours_estimate": labor_hours,
        "repair_estimate_usd": repair_estimate,
        "pieces_in_shipment": pieces_in_shipment,
    }
    try:
        result = api.get_max_bid(payload)
    except Exception as e:
        st.error(f"API error: {e}")
        st.stop()

    st.divider()

    # Results table
    tiers = ["fast", "standard", "patient"]
    rows = []
    for tier in tiers:
        if tier in result:
            t = result[tier]
            max_jpy = t.get("max_bid_jpy", 0)
            max_usd = t.get("max_auction_usd", 0)
            rows.append({
                "Tier":          tier.title(),
                "Max Bid (JPY)": f"¥{max_jpy:,.0f}" if max_jpy > 0 else "—",
                "Max Bid (USD)": f"${max_usd:,.2f}" if max_usd > 0 else "—",
                "Target Profit": f"${t['profit_target']:.0f}",
                "Viable":        "✓" if max_jpy > 0 else "✗",
            })

    if rows:
        results_df = pd.DataFrame(rows)
        st.dataframe(results_df, hide_index=True, width='content')

    # Breakdown
    breakdown = result.get("breakdown", {})
    if breakdown:
        st.caption(
            f"Expected sale: ${breakdown.get('expected_sale_usd',0):.2f}  ·  "
            f"eBay rate: {breakdown.get('ebay_effective_rate',0)*100:.1f}%  ·  "
            f"Labor est.: ${breakdown.get('labor_estimate',0):.2f}  ·  "
            f"Repair est.: ${breakdown.get('repair_estimate',0):.2f}  ·  "
            f"FX: {fx_rate:.0f}"
        )

    # Interpretation hint
    viable = [r for r in rows if r["Viable"] == "✓"]
    not_viable = [r for r in rows if r["Viable"] == "✗"]
    if not viable:
        st.error(
            "No tier is viable at this sale price. The watch would need to sell higher, "
            "or costs (shipping, repairs) need to come down."
        )
    elif not_viable:
        highest_viable = viable[-1]
        st.info(
            f"At this sale price you can target up to the **{highest_viable['Tier']}** tier. "
            f"Max bid: **{highest_viable['Max Bid (JPY)']}**. "
            f"If the auction goes above that, walk away."
        )
    else:
        st.success(
            f"All tiers viable. Patient tier max bid: **{rows[-1]['Max Bid (JPY)']}**."
        )
