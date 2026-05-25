import json
from models import additional_cost_item, now_iso
from db import get_item, put_item, query_pk, update_fields, api_response


def handler(event, context):
    watch_id = event["pathParameters"]["id"]
    body = json.loads(event.get("body", "{}"))

    watch = get_item(f"W#{watch_id}", "META")
    if not watch:
        return api_response(404, {"error": "Watch not found"})

    if "amount_usd" not in body:
        return api_response(400, {"error": "amount_usd is required"})

    cost = additional_cost_item(watch_id, body)
    put_item(cost)

    # Recalculate total additional costs
    all_costs = query_pk(f"W#{watch_id}", "ADDCOST#")
    total = sum(c.get("amount_usd", 0) for c in all_costs)

    # Recalculate landed cost
    auction = watch.get("auction_price_usd") or 0
    customs = watch.get("customs_duty_usd") or 0
    intl = watch.get("intl_shipping_usd") or 0
    buyee_jpy = (
        (watch.get("buyee_platform_jpy") or 0)
        + (watch.get("buyee_inspection_jpy") or 0)
        + (watch.get("domestic_shipping_jpy") or 0)
    )
    jpy_rate = 0
    if watch.get("auction_price_jpy") and watch.get("auction_price_usd"):
        jpy_rate = watch["auction_price_usd"] / watch["auction_price_jpy"]
    buyee_usd = buyee_jpy * jpy_rate if jpy_rate else 0
    landed = round(auction + customs + intl + buyee_usd + total, 2)

    update_fields(f"W#{watch_id}", "META", {
        "total_additional_costs_usd": round(total, 2),
        "total_landed_cost_usd": landed,
        "updated_at": now_iso(),
    })

    return api_response(201, {
        "watch_id": watch_id,
        "cost_id": cost["cost_id"],
        "total_additional_costs": round(total, 2),
        "total_landed_cost": landed,
    })
