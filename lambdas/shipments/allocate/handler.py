import json
from db import get_item, query_pk, update_fields, api_response
from models import now_iso


def handler(event, context):
    shipment_id = event["pathParameters"]["id"]
    shipment = get_item(f"SHIP#{shipment_id}", "META")
    if not shipment:
        return api_response(404, {"error": "Shipment not found"})

    # Get all watch links for this shipment
    links = query_pk(f"SHIP#{shipment_id}", "W#")
    if not links:
        return api_response(400, {"error": "No watches linked to this shipment"})

    total_cost = shipment["total_cost_usd"]
    total_auction_jpy = sum(l["auction_price_jpy"] for l in links)

    if total_auction_jpy == 0:
        return api_response(400, {"error": "Total auction price is zero, cannot allocate"})

    allocations = []
    for link in links:
        weight = link["auction_price_jpy"] / total_auction_jpy
        allocated = round(total_cost * weight, 2)
        watch_id = link["watch_id"]

        # Update the watch record with allocated shipping
        watch = get_item(f"W#{watch_id}", "META")
        if watch:
            update_fields(f"W#{watch_id}", "META", {
                "intl_shipping_usd": allocated,
                "shipment_id": shipment_id,
                "updated_at": now_iso(),
            })
            # Recalc landed cost
            auction = watch.get("auction_price_usd") or 0
            customs = watch.get("customs_duty_usd") or 0
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
            landed = round(auction + customs + allocated + buyee_usd + additional, 2)
            update_fields(f"W#{watch_id}", "META", {"total_landed_cost_usd": landed})

        allocations.append({
            "watch_id": watch_id,
            "auction_price_jpy": link["auction_price_jpy"],
            "weight": round(weight, 4),
            "allocated_usd": allocated,
        })

    return api_response(200, {
        "shipment_id": shipment_id,
        "total_cost_usd": total_cost,
        "allocations": allocations,
    })
