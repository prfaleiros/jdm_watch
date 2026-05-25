from models import now_iso
from db import get_item, delete_item, update_fields, query_pk, api_response


def _recalc(watch_id: str, watch: dict) -> tuple[float, float]:
    all_costs = query_pk(f"W#{watch_id}", "ADDCOST#")
    total = round(sum(c.get("amount_usd", 0) for c in all_costs), 2)

    auction = watch.get("auction_price_usd") or 0
    customs = watch.get("customs_duty_usd") or 0
    intl = watch.get("intl_shipping_usd") or 0
    buyee_jpy = (
        (watch.get("buyee_platform_jpy") or 0)
        + (watch.get("buyee_inspection_jpy") or 0)
        + (watch.get("domestic_shipping_jpy") or 0)
    )
    jpy_rate = (
        watch["auction_price_usd"] / watch["auction_price_jpy"]
        if watch.get("auction_price_jpy") and watch.get("auction_price_usd") else 0
    )
    buyee_usd = buyee_jpy * jpy_rate if jpy_rate else 0
    landed = round(auction + customs + intl + buyee_usd + total, 2)
    return total, landed


def handler(event, context):
    watch_id = event["pathParameters"]["id"]
    cost_id  = event["pathParameters"]["cost_id"]

    if not get_item(f"W#{watch_id}", f"ADDCOST#{cost_id}"):
        return api_response(404, {"error": "Cost not found"})

    delete_item(f"W#{watch_id}", f"ADDCOST#{cost_id}")

    watch = get_item(f"W#{watch_id}", "META")
    total, landed = _recalc(watch_id, watch)
    update_fields(f"W#{watch_id}", "META", {
        "total_additional_costs_usd": total,
        "total_landed_cost_usd": landed,
        "updated_at": now_iso(),
    })

    return api_response(200, {
        "cost_id": cost_id,
        "total_additional_costs_usd": total,
        "total_landed_cost_usd": landed,
    })
