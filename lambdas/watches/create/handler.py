import json
from models import watch_item, stage_transition_item, now_iso
from db import put_item, update_fields, api_response


def recalc_landed_cost(watch: dict) -> float:
    auction = watch.get("auction_price_usd") or 0
    customs = watch.get("customs_duty_usd") or 0
    intl = watch.get("intl_shipping_usd") or 0
    additional = watch.get("total_additional_costs_usd") or 0
    buyee_jpy = (
        (watch.get("buyee_platform_jpy") or 0)
        + (watch.get("buyee_inspection_jpy") or 0)
        + (watch.get("domestic_shipping_jpy") or 0)
    )
    jpy_rate = 0
    if watch.get("auction_price_jpy") and watch.get("auction_price_usd"):
        jpy_rate = watch["auction_price_usd"] / watch["auction_price_jpy"]
    buyee_usd = buyee_jpy * jpy_rate if jpy_rate else 0
    return round(auction + customs + intl + buyee_usd + additional, 2)


def handler(event, context):
    body = json.loads(event.get("body", "{}"))
    item = watch_item(body)
    item["total_landed_cost_usd"] = recalc_landed_cost(item)
    put_item(item)

    transition = stage_transition_item(item["watch_id"], {
        "from_status": "",
        "to_status": item["current_status"],
        "hours_spent": 0,
        "notes": "Initial entry",
    })
    put_item(transition)

    return api_response(201, {
        "watch_id": item["watch_id"],
        "status": item["current_status"],
        "total_landed_cost_usd": item["total_landed_cost_usd"],
        "message": "Watch created",
    })