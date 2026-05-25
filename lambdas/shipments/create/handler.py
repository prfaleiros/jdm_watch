import json
from models import shipment_item, shipment_watch_link
from db import put_item, api_response


def handler(event, context):
    body = json.loads(event.get("body", "{}"))

    if "total_cost_usd" not in body:
        return api_response(400, {"error": "total_cost_usd is required"})

    shipment = shipment_item(body)
    put_item(shipment)

    # Link watches if provided
    watch_ids = body.get("watch_ids", [])
    for w in watch_ids:
        link = shipment_watch_link(
            shipment["shipment_id"],
            w["watch_id"],
            w["auction_price_jpy"],
        )
        put_item(link)

    return api_response(201, {
        "shipment_id": shipment["shipment_id"],
        "watches_linked": len(watch_ids),
    })
