import pandas as pd
import streamlit as st

import api
import fees
from watch_picker import watch_picker, reset_picker

st.set_page_config(page_title="Offer Analyzer", layout="centered", page_icon="⌚")
st.title("Offer Analyzer")
st.caption(
    "Evaluate an offer and see counter suggestions in real time — on the platform it came in "
    "on, and what the same profit would look like everywhere else."
)

ELIGIBLE_STATUSES = {"listed"}


@st.cache_data(ttl=60)
def _load_watches():
    return api.list_watches()


try:
    cfg = fees.load_cfg()
except Exception as e:
    st.error(f"Failed to load pricing config: {e}")
    st.stop()

# ── Pick a watch (clickable list — no dropdown) ───────────────────────────────

watch_id = st.session_state.get("offer_watch_id")

if not watch_id:
    try:
        all_watches = _load_watches()
    except Exception as e:
        st.error(f"Failed to load watches: {e}")
        st.stop()
    eligible = [
        w for w in all_watches
        if w.get("current_status") in ELIGIBLE_STATUSES and not w.get("is_personal")
    ]
    picked = watch_picker(
        eligible, key="offer", status_filter=False, empty_msg="No listed watches found.",
    )
    if picked:
        st.session_state["offer_watch_id"] = picked[0]
        st.rerun()
    st.stop()

if st.button("← All listed watches"):
    st.session_state.pop("offer_watch_id", None)
    reset_picker("offer")
    st.rerun()


@st.cache_data(ttl=60)
def _load(wid):
    return api.get_watch(wid)


try:
    watch = _load(watch_id)
except Exception as e:
    st.error(f"Failed to load watch data: {e}")
    st.stop()

# ── Watch summary ──────────────────────────────────────────────────────────────
name = f"{watch.get('brand', '')} {watch.get('collection', '')} {watch.get('reference', '')}".strip()

hdr_img, hdr_text = st.columns([1, 6])
if watch.get("thumbnail_url"):
    hdr_img.image(watch["thumbnail_url"], width=90)
with hdr_text:
    st.subheader(name)
    st.caption(f"ID: `{watch_id}`")

plat_ids = list(fees.platforms(cfg))

# ── Offer input ────────────────────────────────────────────────────────────────
oc1, oc2 = st.columns([2, 1])
offer_platform = oc2.selectbox(
    "Offer came in on", plat_ids,
    index=plat_ids.index("ebay") if "ebay" in plat_ids else 0,
    format_func=lambda p: fees.platform_label(cfg, p),
)

with st.expander("Adjust fees"):
    fc1, fc2, fc3 = st.columns(3)
    tax_pct = fc1.number_input(
        "Buyer sales tax %", min_value=0.0, max_value=15.0,
        value=fees.default_tax_pct(cfg), step=0.25, format="%.2f",
        help="Varies by state/county. Platform fees are charged on price + tax.",
    )
    ad_pct = fc2.slider(
        "Ad rate (%)", 0.0, 20.0, fees.default_ad_pct(cfg), 0.5,
        help="Promoted Listings rate — only affects platforms that support ads (eBay).",
    )
    ship = fc3.slider(
        "Shipping to buyer ($)", 0.0, 30.0, float(cfg.get("shipping_to_buyer", 6.0)), 0.5,
    )

min_profit = float(cfg.get("min_profit_usd", 20))
priced = fees.forward_price(watch, cfg, tax_pct, ad_pct, ship, min_profit)
bd = priced["breakdown"]
# cost_basis (landed + pre-sale bench costs) is the true cost to weigh an offer against —
# bare total_landed_cost is acquisition-only since the cost-model split and would understate
# cost on any watch with parts/repair costs. forward_price falls back for pre-split records.
cost_basis = bd["total_cost_basis"]
labor_cost = bd["labor_cost"]

mc1, mc2 = st.columns(2)
mc1.metric("Cost Basis", f"${cost_basis:,.2f}")
mc2.metric("Labor", f"${labor_cost:,.2f}")

# Pricing tiers as context, on the platform the offer came in on
st.caption(f"Pricing tiers on {fees.platform_label(cfg, offer_platform)}")
tc = st.columns(3)
for col, tier in zip(tc, ["fast", "standard", "patient"]):
    t = priced[tier]
    col.metric(
        tier.title(), f"${t['prices'][offer_platform]:,.2f}", f"{t['roi_pct']:.0f}% ROI",
        delta_color="off",
    )

st.divider()

offer = oc1.number_input(
    "Offer received ($)",
    min_value=0.0,
    value=float(priced["fast"]["prices"][offer_platform]),
    step=5.0,
    format="%.2f",
    key=f"offer_amt_{watch_id}_{offer_platform}",
)

# ── Verdict on the platform the offer came in on ───────────────────────────────
rows = fees.profit_at_price(cfg, offer, cost_basis, labor_cost, ship, tax_pct, ad_pct)
here = next(r for r in rows if r["id"] == offer_platform)
profit, roi = here["profit"], here["roi_pct"]

rc1, rc2, rc3 = st.columns(3)
rc1.metric("Net Profit", f"${profit:,.2f}")
rc2.metric("ROI", f"{roi:.1f}%")
rc3.metric("Fees", f"${here['fee']:,.2f}")

floor = cost_basis + labor_cost + ship
if profit < 0:
    st.error(f"You'd lose ${abs(profit):.2f} at this offer. Floor is ${floor:.2f} before fees.")
elif roi < 10:
    st.warning(f"Only {roi:.0f}% ROI — thin. Consider countering.")
elif roi < 20:
    st.info(f"{roi:.0f}% ROI — below fast tier. Acceptable if it's been sitting a while.")
else:
    st.success(f"{roi:.0f}% ROI — this offer works.")

# ── Same price vs. same profit, across platforms ───────────────────────────────
st.subheader("Compare platforms")
st.caption(
    "**Same price** shows what this exact price nets on each platform. **Price for same "
    f"profit** is what you could ask elsewhere to net the same \\${profit:,.2f}."
)
cmp_rows = []
for r in rows:
    same_profit_price = fees.price_for_profit(
        cfg, r["id"], profit, cost_basis, labor_cost, ship, tax_pct, ad_pct,
    )
    cmp_rows.append({
        "Platform": r["label"],
        "Fees ($)": r["fee"],
        "Net profit ($)": r["profit"],
        "ROI %": r["roi_pct"],
        "Price for same profit ($)": same_profit_price,
    })
st.dataframe(
    pd.DataFrame(cmp_rows),
    hide_index=True,
    width="stretch",
    column_config={
        "Fees ($)": st.column_config.NumberColumn(format="%.2f"),
        "Net profit ($)": st.column_config.NumberColumn(format="%.2f"),
        "ROI %": st.column_config.NumberColumn(format="%.1f"),
        "Price for same profit ($)": st.column_config.NumberColumn(format="%.2f"),
    },
)

# ── Counter suggestions ────────────────────────────────────────────────────────
st.subheader("Counter at…")
targets = [
    ("Break-even", 0.0),
    (f"${min_profit:,.0f} min profit", min_profit),
] + [
    (f"{priced[t]['roi_pct']:.0f}% ROI ({t})", priced[t]["profit_target"])
    for t in ("fast", "standard", "patient")
]

counter_rows = []
for label, target in targets:
    row = {"Counter at": label}
    for pid in plat_ids:
        row[fees.platform_label(cfg, pid)] = fees.price_for_profit(
            cfg, pid, target, cost_basis, labor_cost, ship, tax_pct, ad_pct,
        )
    gap = row[fees.platform_label(cfg, offer_platform)] - offer
    row[f"vs. offer on {fees.platform_label(cfg, offer_platform)}"] = (
        "✓ offer clears this" if gap <= 0 else f"counter +${gap:,.2f}"
    )
    counter_rows.append(row)

st.dataframe(
    pd.DataFrame(counter_rows),
    hide_index=True,
    width="stretch",
    column_config={
        fees.platform_label(cfg, pid): st.column_config.NumberColumn(format="%.2f")
        for pid in plat_ids
    },
)
