from db import get_item, query_pk, update_fields, api_response
from models import now_iso
from config import load_config
from costs import recalc_landed, total_cost_basis, recalc_profit


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

    cfg = load_config()
    allocations = []
    for link in links:
        weight = link["auction_price_jpy"] / total_auction_jpy
        allocated = round(total_cost * weight, 2)
        watch_id = link["watch_id"]

        watch = get_item(f"W#{watch_id}", "META")
        if watch:
            merged = {**watch, "intl_shipping_usd": allocated}
            landed = recalc_landed(merged)
            presale = watch.get("total_presale_costs_usd") or 0
            cost_basis = total_cost_basis(landed, presale)
            merged["total_landed_cost_usd"] = landed
            net_profit = recalc_profit(merged, cfg)

            watch_updates = {
                "intl_shipping_usd": allocated,
                "shipment_id": shipment_id,
                "total_landed_cost_usd": landed,
                "total_cost_basis_usd": cost_basis,
                "updated_at": now_iso(),
            }
            if net_profit is not None:
                watch_updates["net_profit_usd"] = net_profit
            update_fields(f"W#{watch_id}", "META", watch_updates)

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
