import re

import streamlit as st
import pandas as pd
import api

st.set_page_config(page_title="Bid Calculator", layout="wide", page_icon="⌚")
st.title("Bid Calculator")
st.caption(
    "Enter what you expect to sell the watch for and the shipping context. "
    "The calculator tells you the maximum you should bid at auction in JPY to hit each profit tier."
)

MARKET_RESEARCH_PROMPT = """\
You're researching resale market value for a JDM (Japan Domestic Market) watch reseller \
who buys at Japanese auction and sells on eBay/Reddit in the US. They've described a watch \
they're considering bidding on:

"{description}"

Search eBay, Chrono24, and Reddit (r/watchexchange) for comparable listings — the same \
reference/model where possible, or the closest realistic equivalent if the description is \
loose. Prefer recently SOLD/completed listings over active asking prices when you can find \
them (active listings overstate what things actually sell for). For each comp you use, note: \
source, title, price, currency, seller/ship-from location, listed shipping cost, and a link.

Apples-to-apples adjustment (this is the part that matters most): a domestic-US listing at \
face price is directly comparable to what this reseller could realistically net. An overseas \
listing (Japan, elsewhere in Asia, Europe, etc.) should be treated as effectively costing \
roughly 10-20% more than its face price once you account for typical import/customs friction, \
longer transit risk, and weaker buyer-protection recourse — use your judgment within that \
range based on the specific listing (an established dealer with DDP shipping and strong \
feedback leans low; an informal or unclear overseas seller leans high). State this adjustment \
explicitly per comp, don't just apply it silently.

Weigh condition, box/papers, and any notable variants mentioned in the comps against what was \
described — flag if a comp isn't a great match rather than treating it as equivalent.

If the searches run out before you've found solid comps, don't fabricate specific listings, \
prices, or links — say so plainly and give your best knowledge-based estimate instead, clearly \
flagged as not backed by live comps.

Give a realistic estimated resale price range for this watch in current condition as described, \
not a rare-mint outlier. Structure your response as:
1. A short table or list of the comps you found and used, with your per-comp adjustment noted
2. Your reasoning for the final range (2-4 sentences)
3. End with EXACTLY one line, no other text on it, in this format:
ESTIMATE: $<low>-$<high>
"""


def _research_market_value(description: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])

    # Tuned from live testing: 10/10 max_uses runs ~3min, ~$1.50-2/query, and can still run out
    # of output budget before writing an answer. 4/4 sometimes burns the whole search budget
    # before ever fetching a page, falling back to a no-comps estimate. 6 search / 4 fetch is a
    # reasonable middle ground — still not fully deterministic run to run (agentic search never
    # is), but noticeably more reliable in practice.
    with client.messages.stream(
        model="claude-sonnet-5",
        max_tokens=16000,
        output_config={"effort": "medium"},
        tools=[
            {"type": "web_search_20260209", "name": "web_search", "max_uses": 6},
            {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 4},
        ],
        messages=[{"role": "user", "content": MARKET_RESEARCH_PROMPT.format(description=description)}],
    ) as stream:
        response = stream.get_final_message()

    return "".join(block.text for block in response.content if block.type == "text")


# ── Market Research ─────────────────────────────────────────────────────────
st.subheader("🔍 Market Research")
st.caption(
    "Describe the watch — model, reference, or just \"diver automatic Seiko 5 from the 90s "
    "with original bracelet\" — and Claude searches eBay/Chrono24/Reddit for comps and "
    "estimates a realistic resale range, adjusted for domestic-vs-overseas shipping/import "
    "friction. Feeds the Expected Sale Price below. **Takes 1-2 minutes** — it's doing several "
    "real searches, not a canned lookup. Occasionally it won't find solid comps in time and "
    "falls back to a knowledge-based estimate instead — it'll say so plainly when that happens, "
    "rather than making up fake listings."
)
description = st.text_area(
    "Describe the watch", height=80,
    placeholder="e.g. Seiko Brightz SAGZ083, titanium, radio solar, good condition with box",
)
if st.button("Research Market Value", type="primary", disabled=not description.strip()):
    with st.spinner("Searching eBay, Chrono24, and Reddit… this takes 1-2 minutes."):
        try:
            st.session_state["market_research_result"] = _research_market_value(description)
        except Exception as e:
            st.error(f"Research failed: {e}")

if st.session_state.get("market_research_result"):
    result_text = st.session_state["market_research_result"]
    # st.markdown treats bare $...$ as inline KaTeX math by default, which mangles any AI
    # response full of dollar amounts (e.g. "$239 landed ... **$275" gets parsed as a math
    # span between the two $). This text is never meant to contain real LaTeX, so escape
    # every dollar sign unconditionally rather than fighting selective math-mode detection.
    st.markdown(result_text.replace("$", "\\$"))

    m = re.search(r"ESTIMATE:\s*\$?([\d,.]+)\s*-\s*\$?([\d,.]+)", result_text)
    if m:
        low, high = float(m.group(1).replace(",", "")), float(m.group(2).replace(",", ""))
        midpoint = round((low + high) / 2, 2)
        rc1, rc2 = st.columns([2, 1])
        rc1.info(f"Estimated range: **\\${low:,.0f} – \\${high:,.0f}**  ·  midpoint: **\\${midpoint:,.0f}**")
        if rc2.button("Use midpoint as Expected Sale Price ↓"):
            st.session_state["bid_calc_expected_sale"] = midpoint
            st.rerun()

st.divider()

with st.form("bid_calc"):
    st.subheader("Expected Sale")
    bc1, bc2 = st.columns(2)
    expected_sale = bc1.number_input(
        "Expected sale price (USD) *",
        min_value=1.0, step=5.0, format="%.2f",
        key="bid_calc_expected_sale",
        help="What do you realistically think this will sell for on eBay? Use a comparable "
             "listing as reference, or the Market Research estimate above.",
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

    st.subheader("Custom Profit Range")
    st.caption(
        "The Fast/Standard/Patient tiers below are fixed to your default ROI% and $50 floor — "
        "handy as a reference, but they can undersell what's actually acceptable on a cheap "
        "piece. Set your own min/max here to see the real bid spread."
    )
    profit_unit = st.radio(
        "Target profit as", ["% of sale", "$ flat"], horizontal=True, key="profit_unit",
    )
    if profit_unit == "% of sale":
        profit_pct_range = st.slider(
            "Acceptable profit range (% of expected sale)",
            min_value=0, max_value=100, value=(10, 40), step=1,
        )
    else:
        profit_usd_range = st.slider(
            "Acceptable profit range (USD)",
            min_value=0, max_value=500, value=(30, 150), step=5,
        )

    submitted = st.form_submit_button("Calculate Max Bid", type="primary")

if submitted:
    if profit_unit == "% of sale":
        custom_min = expected_sale * profit_pct_range[0] / 100
        custom_max = expected_sale * profit_pct_range[1] / 100
    else:
        custom_min, custom_max = profit_usd_range

    payload = {
        "expected_sale_usd": expected_sale,
        "fx_rate": fx_rate,
        "labor_hours_estimate": labor_hours,
        "repair_estimate_usd": repair_estimate,
        "pieces_in_shipment": pieces_in_shipment,
        "custom_profit_targets": {"min": custom_min, "max": custom_max},
    }
    try:
        result = api.get_max_bid(payload)
    except Exception as e:
        st.error(f"API error: {e}")
        st.stop()

    st.divider()

    # Custom range — the min-profit end gives the aggressive (higher) bid ceiling, the
    # max-profit end gives the conservative (lower) one.
    custom_min_r = result.get("custom_min", {})
    custom_max_r = result.get("custom_max", {})
    if custom_min_r or custom_max_r:
        st.subheader("Your Custom Range")
        cr1, cr2 = st.columns(2)
        max_bid_jpy = custom_min_r.get("max_bid_jpy", 0)
        cr1.metric(
            f"Bid ceiling for ${custom_min:,.0f} min profit",
            f"¥{max_bid_jpy:,.0f}" if max_bid_jpy > 0 else "Not viable",
            help="The most aggressive bid — clears only your minimum acceptable profit.",
        )
        min_bid_jpy = custom_max_r.get("max_bid_jpy", 0)
        cr2.metric(
            f"Bid ceiling for ${custom_max:,.0f} target profit",
            f"¥{min_bid_jpy:,.0f}" if min_bid_jpy > 0 else "Not viable",
            help="The conservative bid — leaves room for your full target profit.",
        )
        st.caption(
            f"Realistic range to bid within: **¥{min_bid_jpy:,.0f} – ¥{max_bid_jpy:,.0f}**"
            if min_bid_jpy > 0 and max_bid_jpy > 0 else
            "Neither end of this profit range is viable at this sale price — lower the range or raise the expected sale."
        )
        st.divider()

    # Fixed-tier results table (reference)
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
