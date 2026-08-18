import json
from models import additional_cost_item, now_iso
from db import get_item, put_item, query_pk, update_fields, api_response
from config import load_config
from costs import recalc_landed, split_addcost_totals, total_cost_basis, recalc_profit


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

    all_costs = query_pk(f"W#{watch_id}", "ADDCOST#")
    presale, additional = split_addcost_totals(all_costs)
    landed = recalc_landed(watch)
    cost_basis = total_cost_basis(landed, presale)

    # net_profit_usd wasn't recalculated here before (pre-existing gap) — fix it while
    # touching this code, so adding/editing a cost on an already-sold watch stays in sync.
    merged = {**watch, "total_landed_cost_usd": landed, "total_additional_costs_usd": additional}
    net_profit = recalc_profit(merged, load_config())

    updates = {
        "total_additional_costs_usd": additional,
        "total_presale_costs_usd": presale,
        "total_landed_cost_usd": landed,
        "total_cost_basis_usd": cost_basis,
        "updated_at": now_iso(),
    }
    if net_profit is not None:
        updates["net_profit_usd"] = net_profit
    update_fields(f"W#{watch_id}", "META", updates)

    return api_response(201, {
        "watch_id": watch_id,
        "cost_id": cost["cost_id"],
        "total_additional_costs": additional,
        "total_presale_costs_usd": presale,
        "total_landed_cost": landed,
        "total_cost_basis_usd": cost_basis,
    })
