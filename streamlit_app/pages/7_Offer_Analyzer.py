import streamlit as st
import api
from constants import STATUS_LABELS

st.set_page_config(page_title="Offer Analyzer", layout="centered", page_icon="⌚")
st.title("Offer Analyzer")
st.caption("Evaluate an eBay offer and see counter suggestions in real time.")

ELIGIBLE_STATUSES = {"listed"}


@st.cache_data(ttl=60)
def _load_watches():
    return api.list_watches()


try:
    all_watches = _load_watches()
except Exception as e:
    st.error(f"Failed to load watches: {e}")
    st.stop()

eligible = [
    w for w in all_watches
    if w.get("current_status") in ELIGIBLE_STATUSES and not w.get("is_personal")
]

if not eligible:
    st.info("No listed watches found.")
    st.stop()


def _label(w):
    wid = w.get("watch_id", "")[-6:].upper()
    return f"{w.get('brand', '')} {w.get('collection', '')} {w.get('reference', '')} [{wid}]"


watch_id = st.selectbox(
    "Watch",
    [w["watch_id"] for w in eligible],
    format_func=lambda wid: _label(next(w for w in eligible if w["watch_id"] == wid)),
)


@st.cache_data(ttl=60)
def _load(wid):
    return api.get_watch(wid), api.get_pricing(wid)


try:
    watch, pricing = _load(watch_id)
except Exception as e:
    st.error(f"Failed to load watch data: {e}")
    st.stop()

bd = pricing.get("breakdown", {})
landed      = float(bd.get("total_landed_cost", watch.get("total_landed_cost_usd", 0)))
labor_cost  = float(bd.get("labor_cost", 0))
base_ship   = float(bd.get("shipping_to_buyer", 6.0))
ebay_eff    = float(bd.get("ebay_effective_rate", 0.215))
ad_rate_pct = float(bd.get("ad_rate_pct", 5.0))
# FVF × (1 + tax_blend) component — stays fixed when user adjusts the ad rate
base_rate   = ebay_eff - ad_rate_pct / 100

# ── Watch summary ──────────────────────────────────────────────────────────────
name = f"{watch.get('brand', '')} {watch.get('collection', '')} {watch.get('reference', '')}".strip()
st.subheader(name)

mc1, mc2 = st.columns(2)
mc1.metric("Landed Cost", f"${landed:,.2f}")
mc2.metric("Labor", f"${labor_cost:,.2f}")

# Pricing tiers as context
st.caption("Pricing tiers (at configured rates)")
tc1, tc2, tc3 = st.columns(3)
for col, tier in zip([tc1, tc2, tc3], ["fast", "standard", "patient"]):
    t = pricing.get(tier, {})
    col.metric(
        tier.title(),
        f"${t.get('ebay_price', 0):,.2f}",
        f"{t.get('roi_pct', 0):.0f}% ROI",
        delta_color="off",
    )

st.divider()

# ── Offer input ────────────────────────────────────────────────────────────────
fast_price = float(pricing.get("fast", {}).get("ebay_price", landed * 1.2))
offer = st.number_input(
    "Offer received ($)",
    min_value=0.0,
    value=fast_price,
    step=5.0,
    format="%.2f",
)

with st.expander("Adjust fees"):
    adj_ad = st.slider(
        "Ad rate (%)", 0.0, 20.0, float(ad_rate_pct), 0.5,
        help="Override if this listing's Promoted Listings rate differs from your default.",
    )
    adj_ship = st.slider("Shipping to buyer ($)", 0.0, 30.0, float(base_ship), 0.5)

# ── Calculate ──────────────────────────────────────────────────────────────────
eff    = base_rate + adj_ad / 100
net    = offer * (1 - eff) - adj_ship
profit = net - labor_cost - landed
roi    = (profit / landed * 100) if landed > 0 else 0

st.divider()

rc1, rc2 = st.columns(2)
rc1.metric("Net Profit", f"${profit:,.2f}")
rc2.metric("ROI", f"{roi:.1f}%")

if profit < 0:
    st.error(f"You'd lose ${abs(profit):.2f} at this offer. Floor is ${landed + labor_cost + adj_ship:.2f} before fees.")
elif roi < 10:
    st.warning(f"Only {roi:.0f}% ROI — thin. Consider countering.")
elif roi < 20:
    st.info(f"{roi:.0f}% ROI — below fast tier. Acceptable if it's been sitting a while.")
else:
    st.success(f"{roi:.0f}% ROI — this offer works.")

# ── Counter suggestions ────────────────────────────────────────────────────────
st.subheader("Counter at…")

base_cost = landed + labor_cost + adj_ship


def counter_price(target_profit: float) -> float:
    return (base_cost + target_profit) / (1 - eff)


tiers = [
    ("Break-even",         counter_price(0)),
    ("$50 min profit",     counter_price(50)),
    ("20% ROI  (fast)",    counter_price(max(landed * 0.20, 20))),
    ("33% ROI  (std)",     counter_price(max(landed * 0.33, 20))),
    ("50% ROI  (patient)", counter_price(max(landed * 0.50, 20))),
]

for label, price in tiers:
    gap = price - offer
    if gap <= 0:
        st.write(f"✓ **{label}**: ${price:,.2f} — offer clears this")
    else:
        st.write(f"→ **{label}**: ${price:,.2f} *(counter +${gap:.2f})*")
