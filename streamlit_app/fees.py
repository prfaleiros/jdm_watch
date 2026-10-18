"""Platform-aware fee math for the Streamlit pages.

The formulas live in lambdas/shared/python/pricing.py (the backend's source of truth); this
module imports them directly — Streamlit Cloud checks out the whole repo — so what-if pricing
here can never drift from what the Lambdas compute. The platform list and rates come from
config.json via GET /config, so adding a platform is a config edit, not a code change.
"""
import sys
from decimal import Decimal
from pathlib import Path

import streamlit as st

_SHARED = Path(__file__).resolve().parents[1] / "lambdas" / "shared" / "python"
if str(_SHARED) not in sys.path:
    sys.path.append(str(_SHARED))

import pricing as _p  # noqa: E402  (path set up above)

import api  # noqa: E402

# Older sales may carry these; they stay selectable on sale records but aren't priced.
LEGACY_SALE_PLATFORMS = ["direct", "other"]


_BUNDLED_CFG = Path(__file__).resolve().parents[1] / "config" / "config.json"


@st.cache_data(ttl=300)
def _fetch_cfg() -> dict:
    return api.get_config()


def load_cfg() -> dict:
    """Live config from the API; falls back to the repo's config/config.json (Streamlit Cloud
    checks out the whole repo) if the endpoint isn't reachable — e.g. the app redeployed
    before the backend did. Uploaded config is what the Lambdas actually use, so the fallback
    is flagged rather than silent."""
    try:
        return _fetch_cfg()
    except Exception as e:
        import json
        st.warning(f"Couldn't load live pricing config ({e}); using the repo's config.json copy.")
        with open(_BUNDLED_CFG, encoding="utf-8") as f:
            return {k: v for k, v in json.load(f).items() if not k.startswith("_")}


def platforms(cfg: dict) -> dict:
    return _p.get_platforms(cfg)


def platform_label(cfg: dict, pid: str) -> str:
    p = platforms(cfg).get(pid)
    return p["label"] if p else (pid or "").title()


def sale_platform_ids(cfg: dict, current: str = None) -> list:
    """Platforms selectable on a sale record: configured ones, legacy ones, and whatever the
    record already holds (so editing an old sale never silently changes its platform)."""
    ids = list(platforms(cfg))
    ids += [p for p in LEGACY_SALE_PLATFORMS if p not in ids]
    if current and current not in ids:
        ids.append(current)
    return ids


def default_tax_pct(cfg: dict) -> float:
    return float(_p.default_tax_rate(cfg) * 100)


def default_ad_pct(cfg: dict) -> float:
    return float(_p.default_ad_rate(cfg) * 100)


def _plat(cfg: dict, pid: str) -> dict:
    return platforms(cfg)[pid]


def fee_summary(cfg: dict, tax_pct: float, ad_pct: float) -> list:
    """One row per platform: label, % of price taken, flat fee, and whether ads apply."""
    tax, ad = Decimal(str(tax_pct)) / 100, Decimal(str(ad_pct)) / 100
    return [
        {
            "id": pid,
            "label": p["label"],
            "rate_pct": float(_p.variable_rate(p, tax, ad) * 100),
            "flat": float(p["fee_flat"]),
            "ads": p["supports_ads"],
        }
        for pid, p in platforms(cfg).items()
    ]


def profit_at_price(cfg: dict, price: float, cost_basis: float, labor: float,
                    shipping: float, tax_pct: float, ad_pct: float) -> list:
    """What selling at `price` nets on each platform: fee, profit, ROI on cost basis."""
    tax, ad = Decimal(str(tax_pct)) / 100, Decimal(str(ad_pct)) / 100
    price_d = Decimal(str(price))
    out = []
    for pid, p in platforms(cfg).items():
        fee = _p.fee_at_price(p, price_d, tax, ad)
        profit = price_d - fee - Decimal(str(cost_basis)) - Decimal(str(labor)) - Decimal(str(shipping))
        out.append({
            "id": pid,
            "label": p["label"],
            "fee": float(fee),
            "profit": float(profit),
            "roi_pct": float(profit / Decimal(str(cost_basis)) * 100) if cost_basis else 0.0,
        })
    return out


def price_for_profit(cfg: dict, pid: str, profit: float, cost_basis: float, labor: float,
                     shipping: float, tax_pct: float, ad_pct: float) -> float:
    """List price on platform `pid` that nets exactly `profit` after fees and costs."""
    tax, ad = Decimal(str(tax_pct)) / 100, Decimal(str(ad_pct)) / 100
    needed = (Decimal(str(cost_basis)) + Decimal(str(labor))
              + Decimal(str(shipping)) + Decimal(str(profit)))
    return float(_p.price_for_net(_plat(cfg, pid), needed, tax, ad))


def forward_price(watch: dict, cfg: dict, tax_pct: float, ad_pct: float,
                  shipping: float, min_profit: float) -> dict:
    """Tier prices per platform for one watch record, with what-if overrides."""
    return _p.forward_price(watch, cfg, {
        "sales_tax_pct": tax_pct, "ad_rate_pct": ad_pct,
        "shipping_usd": shipping, "min_profit_usd": min_profit,
    })
