import json
from models import now_iso
from db import get_item, update_fields, api_response
from config import load_config
from costs import recalc_landed, recalc_profit, total_cost_basis


# Fields that can be directly updated (not derived)
EDITABLE_FIELDS = {
    "brand", "collection", "reference", "jdm_model", "serial",
    "diameter_mm", "lug_to_lug_mm", "thickness_mm", "lug_width_mm",
    "case_material", "solar", "radio_sync", "color",
    "auction_price_jpy", "auction_price_usd",
    "buyee_platform_jpy", "buyee_inspection_jpy", "domestic_shipping_jpy", "buyee_fees_usd",
    "customs_duty_usd", "shipment_id", "intl_shipping_usd",
    "sale_price_usd", "sale_platform", "sale_date",
    "shipping_cost_usd", "shipping_label_source", "platform_fees_usd",
    "is_personal", "notes", "total_labor_hours", "feature_pitch",
    "water_resistance", "movement_type", "crystal_type",
    "jewel_count", "bracelet_material", "power_reserve",
    "thumbnail_key",
}


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

    # Apply updates to local copy for recalc. total_presale_costs_usd /
    # total_additional_costs_usd are untouched here (this endpoint never changes ADDCOST
    # records), so only landed + cost_basis + profit need recomputing.
    merged = {**watch, **updates}
    updates["total_landed_cost_usd"] = recalc_landed(merged)
    merged["total_landed_cost_usd"] = updates["total_landed_cost_usd"]
    updates["total_cost_basis_usd"] = total_cost_basis(
        updates["total_landed_cost_usd"], merged.get("total_presale_costs_usd") or 0
    )
    merged["total_cost_basis_usd"] = updates["total_cost_basis_usd"]
    net = recalc_profit(merged, cfg)
    if net is not None:
        updates["net_profit_usd"] = net
    updates["updated_at"] = now_iso()

    update_fields(f"W#{watch_id}", "META", updates)
    return api_response(200, {"watch_id": watch_id, "updated_fields": list(updates.keys())})
