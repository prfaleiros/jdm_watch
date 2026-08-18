# Categories incurred before a sale (parts/repairs put into the piece on the bench).
# Everything else ("shipping", "advertising", "other") is NOT auto-classified as pre-sale —
# timing is ambiguous for those, so they stay out of total_presale_costs_usd unless a human
# says otherwise via the Admin tab.
PRESALE_CATEGORIES = {"part", "consumable", "tool"}


def _safe_float(val, default: float = 0.0) -> float:
    """Coerce to float, falling back to `default` instead of raising.

    These recalc functions now run on every watches/update PATCH (not just sale-related
    ones, and not just through the polished forms — the Admin tab's Quick Patch can put any
    text into any field). A single bad non-numeric value must never crash the recalc: that
    would 502 on this watch's *every* future edit, including the one meant to fix it.
    """
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def recalc_landed(watch: dict) -> float:
    """Pure acquisition cost: auction + customs + intl shipping + Buyee fees (JPY->USD).

    Does NOT include any ADDCOST amounts (parts/repairs/ads) — those live in
    total_presale_costs_usd / total_additional_costs_usd instead. See total_cost_basis().
    """
    auction = _safe_float(watch.get("auction_price_usd"))
    customs = _safe_float(watch.get("customs_duty_usd"))
    intl = _safe_float(watch.get("intl_shipping_usd"))
    buyee_jpy = (
        _safe_float(watch.get("buyee_platform_jpy"))
        + _safe_float(watch.get("buyee_inspection_jpy"))
        + _safe_float(watch.get("domestic_shipping_jpy"))
    )
    jpy_rate = 0.0
    auction_jpy = _safe_float(watch.get("auction_price_jpy"))
    if auction_jpy and auction:
        jpy_rate = auction / auction_jpy
    buyee_usd = buyee_jpy * jpy_rate if jpy_rate else 0.0
    return round(auction + customs + intl + buyee_usd, 2)


def split_addcost_totals(addcost_items: list) -> tuple[float, float]:
    """Return (total_presale_usd, total_additional_usd) from a watch's ADDCOST records.

    total_additional_usd is every ADDCOST regardless of category (unchanged meaning from
    before the cost-model split). total_presale_usd is the subset in PRESALE_CATEGORIES.
    """
    presale = 0.0
    additional = 0.0
    for c in addcost_items:
        amt = _safe_float(c.get("amount_usd"))
        additional += amt
        if c.get("category") in PRESALE_CATEGORIES:
            presale += amt
    return round(presale, 2), round(additional, 2)


def total_cost_basis(landed_usd: float, presale_usd: float) -> float:
    """True all-in cost before any sale: acquisition + pre-sale bench costs."""
    return round(_safe_float(landed_usd) + _safe_float(presale_usd), 2)


def recalc_profit(watch: dict, cfg: dict) -> float | None:
    """Net profit after a sale. Unchanged in substance from the pre-split formula:
    sale - fees - shipping - landed - total_additional_costs_usd - labor. Landed no longer
    includes additional costs itself, so additional is subtracted explicitly here instead —
    same total either way.

    Returns None (no profit yet) only when sale_price_usd is genuinely unset — a non-numeric
    sale_price_usd (bad data) is treated as 0 rather than crashing, since this can now be
    called from a generic field patch, not just a real sale.
    """
    if not watch.get("sale_price_usd"):
        return None
    sale = _safe_float(watch["sale_price_usd"])
    fees = _safe_float(watch.get("platform_fees_usd"))
    shipping = _safe_float(watch.get("shipping_cost_usd"))
    landed = _safe_float(watch.get("total_landed_cost_usd"))
    additional = _safe_float(watch.get("total_additional_costs_usd"))
    labor_hours = _safe_float(watch.get("total_labor_hours"))
    labor_rate = _safe_float(cfg.get("labor_rate"), 1.0)
    return round(sale - fees - shipping - landed - additional - (labor_hours * labor_rate), 2)
