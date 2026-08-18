from models import additional_cost_item, now_iso
from db import get_item, put_item, query_pk, update_fields, api_response
from config import load_config
from costs import recalc_landed, split_addcost_totals, total_cost_basis, recalc_profit


def handler(event, context):
    campaign_id = event["pathParameters"]["id"]
    campaign = get_item(f"CAMP#{campaign_id}", "META")
    if not campaign:
        return api_response(404, {"error": "Campaign not found"})

    links = query_pk(f"CAMP#{campaign_id}", "W#")
    if not links:
        return api_response(400, {"error": "No watches linked to this campaign"})

    total_cost = campaign["total_cost_usd"]
    per_watch = round(total_cost / len(links), 2)
    cfg = load_config()

    allocations = []
    for link in links:
        watch_id = link["watch_id"]
        watch = get_item(f"W#{watch_id}", "META")
        if not watch:
            continue

        put_item(additional_cost_item(watch_id, {
            "amount_usd": per_watch,
            "category": "advertising",
            "notes": f"Ad campaign ({campaign.get('platform', 'ebay_offsite')}): "
                     f"{campaign.get('notes', '')} [{campaign_id}]".strip(),
        }))

        all_costs = query_pk(f"W#{watch_id}", "ADDCOST#")
        presale, additional = split_addcost_totals(all_costs)
        landed = recalc_landed(watch)
        cost_basis = total_cost_basis(landed, presale)

        merged = {**watch, "total_landed_cost_usd": landed, "total_additional_costs_usd": additional}
        net_profit = recalc_profit(merged, cfg)

        watch_updates = {
            "total_additional_costs_usd": additional,
            "total_presale_costs_usd": presale,
            "total_landed_cost_usd": landed,
            "total_cost_basis_usd": cost_basis,
            "updated_at": now_iso(),
        }
        if net_profit is not None:
            watch_updates["net_profit_usd"] = net_profit
        update_fields(f"W#{watch_id}", "META", watch_updates)

        allocations.append({"watch_id": watch_id, "allocated_usd": per_watch})

    return api_response(200, {
        "campaign_id": campaign_id,
        "total_cost_usd": total_cost,
        "watches": len(links),
        "per_watch_usd": per_watch,
        "allocations": allocations,
    })
