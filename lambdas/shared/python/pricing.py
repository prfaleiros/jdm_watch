from decimal import Decimal, ROUND_HALF_UP


def _d(val) -> Decimal:
    if val is None:
        return Decimal("0")
    return Decimal(str(val))


def ebay_effective_rate(cfg: dict) -> Decimal:
    fvf = _d(cfg.get("ebay_fvf_rate", "0.15"))
    tax = _d(cfg.get("sales_tax_blend", "0.10"))
    # ad rate stored as a percentage (e.g. "5") — convert to decimal
    ad  = _d(cfg.get("default_ad_rate_pct", "0")) / Decimal("100")
    return fvf * (Decimal("1") + tax) + ad


def _roi_targets(cfg: dict) -> dict:
    """Return per-tier ROI as Decimal fractions (0.20, 0.33, 0.50)."""
    return {
        "fast":     _d(cfg.get("target_roi_pct_fast",     "20")) / Decimal("100"),
        "standard": _d(cfg.get("target_roi_pct_standard", "33")) / Decimal("100"),
        "patient":  _d(cfg.get("target_roi_pct_patient",  "50")) / Decimal("100"),
    }


def forward_price(watch: dict, cfg: dict) -> dict:
    """Given a watch with known costs, calculate sale price targets per tier.

    Profit target = max(cost_basis × roi_pct, min_profit_floor)
    This ensures the target scales with capital at risk while protecting
    small purchases from being priced below minimum viable margin.

    cost_basis = landed (acquisition) + pre-sale bench costs (parts/repairs) — see
    lambdas/shared/python/costs.py. Falls back to bare landed for watches predating the
    cost-basis split (total_cost_basis_usd not yet populated).
    """
    landed      = _d(watch.get("total_landed_cost_usd", 0))
    cost_basis  = _d(watch.get("total_cost_basis_usd") or watch.get("total_landed_cost_usd", 0))
    labor_hours = _d(watch.get("total_labor_hours", 0))
    labor_rate  = _d(cfg.get("labor_rate", "1"))
    labor_cost  = labor_hours * labor_rate
    shipping    = _d(cfg.get("shipping_to_buyer", "6"))
    min_profit  = _d(cfg.get("min_profit_usd", "20"))

    ebay_eff = ebay_effective_rate(cfg)
    pp_rate  = _d(cfg.get("paypal_rate", "0.029"))
    pp_flat  = _d(cfg.get("paypal_flat", "0.30"))
    roi_map  = _roi_targets(cfg)

    base_cost = cost_basis + labor_cost + shipping

    results = {}
    for label, roi in roi_map.items():
        # Scale profit with capital; floor prevents unprofitable small sales
        target = max(cost_basis * roi, min_profit)

        ebay_price   = (base_cost + target) / (Decimal("1") - ebay_eff)
        reddit_price = (base_cost + target + pp_flat) / (Decimal("1") - pp_rate)

        results[label] = {
            "profit_target": float(target.quantize(Decimal("0.01"), ROUND_HALF_UP)),
            "roi_pct":       float((roi * 100).quantize(Decimal("0.1"), ROUND_HALF_UP)),
            "ebay_price":    float(ebay_price.quantize(Decimal("0.01"), ROUND_HALF_UP)),
            "reddit_price":  float(reddit_price.quantize(Decimal("0.01"), ROUND_HALF_UP)),
        }

    results["breakdown"] = {
        "total_landed_cost":  float(landed),
        "total_cost_basis":   float(cost_basis),
        "labor_cost":         float(labor_cost),
        "shipping_to_buyer":  float(shipping),
        "ebay_effective_rate":float(ebay_eff.quantize(Decimal("0.00001"))),
        "ad_rate_pct":        float(_d(cfg.get("default_ad_rate_pct", "0"))),
        "min_profit_usd":     float(min_profit),
    }
    return results


def backward_max_bid(params: dict, cfg: dict) -> dict:
    """Given an expected sale price, calculate the maximum auction bid per tier.

    Works backwards:
      net_revenue = sale × (1 − ebay_eff) − shipping
      available   = net_revenue − labor − repairs
      total_landed is constrained so that profit = available − total_landed
        satisfies both: profit ≥ landed × roi  AND  profit ≥ min_profit
      The binding constraint is the one that requires a lower total_landed
      (i.e. more conservative bid).
    """
    expected_sale = _d(params["expected_sale_usd"])
    repair_est    = _d(params.get("repair_estimate_usd", 0))
    labor_hrs     = _d(params.get("labor_hours_estimate", 0))
    pieces        = _d(params.get("pieces_in_shipment", 1))
    fx            = _d(params["fx_rate"])

    labor_rate  = _d(cfg.get("labor_rate", "1"))
    ebay_eff    = ebay_effective_rate(cfg)
    shipping    = _d(cfg.get("shipping_to_buyer", "6"))
    customs     = _d(cfg.get("customs_rate", "0.15"))
    min_profit  = _d(cfg.get("min_profit_usd", "20"))

    buyee_plat  = _d(cfg.get("buyee_platform_jpy",    "500"))
    buyee_insp  = _d(cfg.get("buyee_service_jpy",     "500"))
    domestic    = _d(cfg.get("domestic_shipping_jpy", "900"))
    intl_est    = _d(params.get("intl_ship_estimate_usd",
                                cfg.get("intl_ship_estimate_usd", "40")))

    roi_map = _roi_targets(cfg)

    # Fixed JPY-side costs converted to USD
    buyee_fixed_usd = (buyee_plat + buyee_insp + domestic) / fx
    intl_alloc      = intl_est / pieces

    net_revenue = expected_sale * (Decimal("1") - ebay_eff) - shipping
    available   = net_revenue - (labor_hrs * labor_rate) - repair_est

    results = {}
    for label, roi in roi_map.items():
        # ROI constraint: profit = landed × roi  →  landed = available / (1 + roi)
        landed_from_roi   = available / (Decimal("1") + roi)
        # Floor constraint: profit = min_profit  →  landed = available − min_profit
        landed_from_floor = available - min_profit
        # Use the more conservative (lower) landed → lower max bid
        total_landed = min(landed_from_roi, landed_from_floor)

        max_auction_usd = (total_landed - buyee_fixed_usd - intl_alloc) / (Decimal("1") + customs)
        max_bid_jpy     = max_auction_usd * fx
        actual_profit   = available - total_landed

        results[label] = {
            "roi_pct":          float((roi * 100).quantize(Decimal("0.1"), ROUND_HALF_UP)),
            "profit_target":    float(actual_profit.quantize(Decimal("0.01"), ROUND_HALF_UP)),
            "max_auction_usd":  float(max_auction_usd.quantize(Decimal("0.01"), ROUND_HALF_UP)),
            "max_bid_jpy":      float(max_bid_jpy.quantize(Decimal("1"), ROUND_HALF_UP)),
        }

    # Optional custom profit targets (e.g. {"min": 30, "max": 150} in USD) — lets the caller
    # explore a self-chosen profit range instead of only the three fixed ROI tiers, which are
    # dominated by min_profit_usd on cheap watches and can undersell what's actually viable.
    custom_targets = params.get("custom_profit_targets") or {}
    for label, target_usd in custom_targets.items():
        target = _d(target_usd)
        total_landed = available - target
        max_auction_usd = (total_landed - buyee_fixed_usd - intl_alloc) / (Decimal("1") + customs)
        max_bid_jpy = max_auction_usd * fx
        results[f"custom_{label}"] = {
            "profit_target":   float(target.quantize(Decimal("0.01"), ROUND_HALF_UP)),
            "max_auction_usd": float(max_auction_usd.quantize(Decimal("0.01"), ROUND_HALF_UP)),
            "max_bid_jpy":     float(max_bid_jpy.quantize(Decimal("1"), ROUND_HALF_UP)),
        }

    results["breakdown"] = {
        "expected_sale_usd":   float(expected_sale),
        "ebay_effective_rate": float(ebay_eff.quantize(Decimal("0.00001"))),
        "fx_rate":             float(fx),
        "repair_estimate":     float(repair_est),
        "labor_estimate":      float(labor_hrs * labor_rate),
        "ad_rate_pct":         float(_d(cfg.get("default_ad_rate_pct", "0"))),
    }
    return results
