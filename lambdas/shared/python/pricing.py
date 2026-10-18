from decimal import Decimal, ROUND_HALF_UP

ONE = Decimal("1")


def _d(val) -> Decimal:
    if val is None:
        return Decimal("0")
    return Decimal(str(val))


def _bool(val, default: bool) -> bool:
    if val is None:
        return default
    if isinstance(val, str):
        return val.strip().lower() in ("1", "true", "yes")
    return bool(val)


def _q(val: Decimal, places: str = "0.01") -> float:
    return float(val.quantize(Decimal(places), ROUND_HALF_UP))


# ── Sale platforms ────────────────────────────────────────────────────────────

def get_platforms(cfg: dict) -> dict:
    """Sale platforms from config.json's `platforms` block, normalized to Decimals.

    Each platform charges `fee_rate` on the sale price (plus the buyer's sales tax when
    `fee_on_tax`) and an optional flat `fee_flat_usd` per sale. `supports_ads` marks platforms
    where the promoted-listing ad rate applies. Falls back to the legacy flat keys
    (ebay_fvf_rate / paypal_*) if `platforms` hasn't been uploaded yet.
    """
    raw = cfg.get("platforms")
    if not raw:
        raw = {
            "ebay": {"label": "eBay", "fee_rate": cfg.get("ebay_fvf_rate", "0.15"),
                     "fee_flat_usd": "0.40", "fee_on_tax": True, "supports_ads": True},
            "reddit": {"label": "Reddit (PayPal)", "fee_rate": cfg.get("paypal_rate", "0.029"),
                       "fee_flat_usd": cfg.get("paypal_flat", "0.30"), "fee_on_tax": False,
                       "supports_ads": False},
        }
    return {
        pid: {
            "id": pid,
            "label": p.get("label", pid),
            "fee_rate": _d(p.get("fee_rate", 0)),
            "fee_flat": _d(p.get("fee_flat_usd", 0)),
            "fee_on_tax": _bool(p.get("fee_on_tax"), True),
            "supports_ads": _bool(p.get("supports_ads"), False),
        }
        for pid, p in raw.items()
    }


def default_tax_rate(cfg: dict) -> Decimal:
    """Default buyer sales tax as a fraction (config stores a percent, e.g. "8")."""
    if "default_sales_tax_pct" in cfg:
        return _d(cfg["default_sales_tax_pct"]) / Decimal("100")
    return _d(cfg.get("sales_tax_blend", "0.08"))  # legacy key was already a fraction


def default_ad_rate(cfg: dict) -> Decimal:
    return _d(cfg.get("default_ad_rate_pct", "0")) / Decimal("100")


def variable_rate(p: dict, tax: Decimal, ad: Decimal) -> Decimal:
    """Share of the sale price the platform takes. The fee base includes sales tax when the
    platform charges on it; the ad rate only applies where the platform supports ads."""
    rate = p["fee_rate"] * (ONE + tax if p["fee_on_tax"] else ONE)
    return rate + (ad if p["supports_ads"] else Decimal("0"))


def fee_at_price(p: dict, price: Decimal, tax: Decimal, ad: Decimal) -> Decimal:
    return price * variable_rate(p, tax, ad) + p["fee_flat"]


def price_for_net(p: dict, net_needed: Decimal, tax: Decimal, ad: Decimal) -> Decimal:
    """List price that leaves `net_needed` after the platform's fees."""
    return (net_needed + p["fee_flat"]) / (ONE - variable_rate(p, tax, ad))


def resolve_overrides(cfg: dict, overrides: dict | None = None):
    """(tax, ad, shipping, min_profit) as Decimals — config defaults with per-call overrides
    on top. Overrides: sales_tax_pct and ad_rate_pct in percent, shipping_usd and
    min_profit_usd in dollars. Blank/None values fall through to config."""
    ov = {k: v for k, v in (overrides or {}).items() if v not in (None, "")}
    tax = _d(ov["sales_tax_pct"]) / Decimal("100") if "sales_tax_pct" in ov else default_tax_rate(cfg)
    ad = _d(ov["ad_rate_pct"]) / Decimal("100") if "ad_rate_pct" in ov else default_ad_rate(cfg)
    shipping = _d(ov["shipping_usd"]) if "shipping_usd" in ov else _d(cfg.get("shipping_to_buyer", "6"))
    min_profit = _d(ov["min_profit_usd"]) if "min_profit_usd" in ov else _d(cfg.get("min_profit_usd", "20"))
    return tax, ad, shipping, min_profit


def _roi_targets(cfg: dict) -> dict:
    """Return per-tier ROI as Decimal fractions (0.20, 0.33, 0.50)."""
    return {
        "fast":     _d(cfg.get("target_roi_pct_fast",     "20")) / Decimal("100"),
        "standard": _d(cfg.get("target_roi_pct_standard", "33")) / Decimal("100"),
        "patient":  _d(cfg.get("target_roi_pct_patient",  "50")) / Decimal("100"),
    }


def forward_price(watch: dict, cfg: dict, overrides: dict | None = None) -> dict:
    """Given a watch with known costs, calculate sale price targets per tier, per platform.

    Profit target = max(cost_basis × roi_pct, min_profit_floor)
    This ensures the target scales with capital at risk while protecting
    small purchases from being priced below minimum viable margin.

    cost_basis = landed (acquisition) + pre-sale bench costs (parts/repairs) — see
    lambdas/shared/python/costs.py. Falls back to bare landed for watches predating the
    cost-basis split (total_cost_basis_usd not yet populated).

    overrides (all optional): sales_tax_pct, ad_rate_pct, shipping_usd, min_profit_usd.
    """
    landed      = _d(watch.get("total_landed_cost_usd", 0))
    cost_basis  = _d(watch.get("total_cost_basis_usd") or watch.get("total_landed_cost_usd", 0))
    labor_hours = _d(watch.get("total_labor_hours", 0))
    labor_rate  = _d(cfg.get("labor_rate", "1"))
    labor_cost  = labor_hours * labor_rate

    tax, ad, shipping, min_profit = resolve_overrides(cfg, overrides)
    plats     = get_platforms(cfg)
    roi_map   = _roi_targets(cfg)
    base_cost = cost_basis + labor_cost + shipping

    results = {}
    for label, roi in roi_map.items():
        # Scale profit with capital; floor prevents unprofitable small sales
        target = max(cost_basis * roi, min_profit)
        prices = {pid: _q(price_for_net(p, base_cost + target, tax, ad)) for pid, p in plats.items()}
        results[label] = {
            "profit_target": _q(target),
            "roi_pct":       _q(roi * 100, "0.1"),
            "prices":        prices,
            # kept for callers that predate multi-platform (eBay draft CSV)
            "ebay_price":    prices.get("ebay"),
            "reddit_price":  prices.get("reddit"),
        }

    results["breakdown"] = {
        "total_landed_cost":  float(landed),
        "total_cost_basis":   float(cost_basis),
        "labor_cost":         float(labor_cost),
        "shipping_to_buyer":  float(shipping),
        "sales_tax_pct":      _q(tax * 100),
        "ad_rate_pct":        _q(ad * 100),
        "min_profit_usd":     float(min_profit),
        "platforms": {
            pid: {
                "label":          p["label"],
                "effective_rate": float(variable_rate(p, tax, ad).quantize(Decimal("0.00001"))),
                "flat_fee_usd":   float(p["fee_flat"]),
            }
            for pid, p in plats.items()
        },
    }
    return results


def backward_max_bid(params: dict, cfg: dict) -> dict:
    """Given an expected sale price, calculate the maximum auction bid per tier.

    Works backwards:
      net_revenue = sale × (1 − platform_rate) − platform_flat_fee − shipping
      available   = net_revenue − labor − repairs
      total_landed is constrained so that profit = available − total_landed
        satisfies both: profit ≥ landed × roi  AND  profit ≥ min_profit
      The binding constraint is the one that requires a lower total_landed
      (i.e. more conservative bid).

    Optional params: `platform` (default eBay) plus the sales_tax_pct / ad_rate_pct overrides.
    """
    expected_sale = _d(params["expected_sale_usd"])
    repair_est    = _d(params.get("repair_estimate_usd", 0))
    labor_hrs     = _d(params.get("labor_hours_estimate", 0))
    pieces        = _d(params.get("pieces_in_shipment", 1))
    fx            = _d(params["fx_rate"])

    labor_rate  = _d(cfg.get("labor_rate", "1"))
    tax, ad, shipping, min_profit = resolve_overrides(cfg, params)
    plats       = get_platforms(cfg)
    platform_id = params.get("platform") or ("ebay" if "ebay" in plats else next(iter(plats)))
    platform    = plats[platform_id]
    eff         = variable_rate(platform, tax, ad)
    customs     = _d(cfg.get("customs_rate", "0.15"))

    buyee_plat  = _d(cfg.get("buyee_platform_jpy",    "500"))
    buyee_insp  = _d(cfg.get("buyee_service_jpy",     "500"))
    domestic    = _d(cfg.get("domestic_shipping_jpy", "900"))
    intl_est    = _d(params.get("intl_ship_estimate_usd",
                                cfg.get("intl_ship_estimate_usd", "40")))

    roi_map = _roi_targets(cfg)

    # Fixed JPY-side costs converted to USD
    buyee_fixed_usd = (buyee_plat + buyee_insp + domestic) / fx
    intl_alloc      = intl_est / pieces

    net_revenue = expected_sale * (ONE - eff) - platform["fee_flat"] - shipping
    available   = net_revenue - (labor_hrs * labor_rate) - repair_est

    results = {}
    for label, roi in roi_map.items():
        # ROI constraint: profit = landed × roi  →  landed = available / (1 + roi)
        landed_from_roi   = available / (ONE + roi)
        # Floor constraint: profit = min_profit  →  landed = available − min_profit
        landed_from_floor = available - min_profit
        # Use the more conservative (lower) landed → lower max bid
        total_landed = min(landed_from_roi, landed_from_floor)

        max_auction_usd = (total_landed - buyee_fixed_usd - intl_alloc) / (ONE + customs)
        max_bid_jpy     = max_auction_usd * fx
        actual_profit   = available - total_landed

        results[label] = {
            "roi_pct":          _q(roi * 100, "0.1"),
            "profit_target":    _q(actual_profit),
            "max_auction_usd":  _q(max_auction_usd),
            "max_bid_jpy":      _q(max_bid_jpy, "1"),
        }

    # Optional custom profit targets (e.g. {"min": 30, "max": 150} in USD) — lets the caller
    # explore a self-chosen profit range instead of only the three fixed ROI tiers, which are
    # dominated by min_profit_usd on cheap watches and can undersell what's actually viable.
    custom_targets = params.get("custom_profit_targets") or {}
    for label, target_usd in custom_targets.items():
        target = _d(target_usd)
        total_landed = available - target
        max_auction_usd = (total_landed - buyee_fixed_usd - intl_alloc) / (ONE + customs)
        max_bid_jpy = max_auction_usd * fx
        results[f"custom_{label}"] = {
            "profit_target":   _q(target),
            "max_auction_usd": _q(max_auction_usd),
            "max_bid_jpy":     _q(max_bid_jpy, "1"),
        }

    results["breakdown"] = {
        "expected_sale_usd":   float(expected_sale),
        "platform":            platform_id,
        "platform_label":      platform["label"],
        "effective_rate":      float(eff.quantize(Decimal("0.00001"))),
        "flat_fee_usd":        float(platform["fee_flat"]),
        "sales_tax_pct":       _q(tax * 100),
        "fx_rate":             float(fx),
        "repair_estimate":     float(repair_est),
        "labor_estimate":      float(labor_hrs * labor_rate),
        "ad_rate_pct":         _q(ad * 100) if platform["supports_ads"] else 0.0,
    }
    return results
