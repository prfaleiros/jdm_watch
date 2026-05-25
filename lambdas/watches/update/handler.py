import json
from models import now_iso
from db import get_item, update_fields, api_response
from config import load_config


# Fields that can be directly updated (not derived)
EDITABLE_FIELDS = {
    "brand", "collection", "reference", "jdm_model", "serial",
    "diameter_mm", "lug_to_lug_mm", "thickness_mm", "lug_width_mm",
    "case_material", "solar", "radio_sync", "color",
    "auction_price_jpy", "auction_price_usd",
    "buyee_platform_jpy", "buyee_inspection_jpy", "domestic_shipping_jpy",
    "customs_duty_usd", "shipment_id", "intl_shipping_usd",
    "sale_price_usd", "sale_platform", "sale_date",
    "shipping_cost_usd", "platform_fees_usd",
    "is_personal", "notes", "total_labor_hours", "feature_pitch",
    "water_resistance", "movement_type", "crystal_type",
    "jewel_count", "bracelet_material", "power_reserve",
    "thumbnail_key",
}


def recalc_landed_cost(watch: dict) -> float:
    auction = watch.get("auction_price_usd") or 0
    customs = watch.get("customs_duty_usd") or 0
    intl = watch.get("intl_shipping_usd") or 0
    additional = watch.get("total_additional_costs_usd") or 0
    # Buyee fees — convert from JPY if we have a USD auction price and JPY auction price
    buyee_fees_jpy = (
        (watch.get("buyee_platform_jpy") or 0)
        + (watch.get("buyee_inspection_jpy") or 0)
        + (watch.get("domestic_shipping_jpy") or 0)
    )
    jpy_rate = 0
    if watch.get("auction_price_jpy") and watch.get("auction_price_usd"):
        jpy_rate = watch["auction_price_usd"] / watch["auction_price_jpy"]
    buyee_fees_usd = buyee_fees_jpy * jpy_rate if jpy_rate else 0

    return round(auction + customs + intl + buyee_fees_usd + additional, 2)


def recalc_net_profit(watch: dict, cfg: dict) -> float | None:
    if not watch.get("sale_price_usd"):
        return None
    sale = watch["sale_price_usd"]
    fees = watch.get("platform_fees_usd") or 0
    shipping = watch.get("shipping_cost_usd") or 0
    landed = watch.get("total_landed_cost_usd") or 0
    labor_hours = watch.get("total_labor_hours") or 0
    labor_rate = float(cfg.get("labor_rate", "1"))
    return round(sale - fees - shipping - landed - (labor_hours * labor_rate), 2)


def handler(event, context):
    watch_id = event["pathParameters"]["id"]
    body = json.loads(event.get("body", "{}"))

    watch = get_item(f"W#{watch_id}", "META")
    if not watch:
        return api_response(404, {"error": "Watch not found"})

    updates = {k: v for k, v in body.items() if k in EDITABLE_FIELDS}
    if not updates:
        return api_response(400, {"error": "No valid fields to update"})

    cfg = load_config()

    # Apply updates to local copy for recalc
    merged = {**watch, **updates}
    updates["total_landed_cost_usd"] = recalc_landed_cost(merged)
    merged["total_landed_cost_usd"] = updates["total_landed_cost_usd"]
    net = recalc_net_profit(merged, cfg)
    if net is not None:
        updates["net_profit_usd"] = net
    updates["updated_at"] = now_iso()

    update_fields(f"W#{watch_id}", "META", updates)
    return api_response(200, {"watch_id": watch_id, "updated_fields": list(updates.keys())})
