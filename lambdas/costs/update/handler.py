import json
from models import now_iso
from db import get_item, update_fields, query_pk, api_response
from config import load_config
from costs import recalc_landed, split_addcost_totals, total_cost_basis, recalc_profit

EDITABLE_FIELDS = {"amount_usd", "category", "notes", "date"}


def handler(event, context):
    watch_id = event["pathParameters"]["id"]
    cost_id  = event["pathParameters"]["cost_id"]
    body = json.loads(event.get("body", "{}"))

    if not get_item(f"W#{watch_id}", f"ADDCOST#{cost_id}"):
        return api_response(404, {"error": "Cost not found"})

    updates = {k: v for k, v in body.items() if k in EDITABLE_FIELDS}
    if not updates:
        return api_response(400, {"error": "No valid fields to update"})

    updates["updated_at"] = now_iso()
    update_fields(f"W#{watch_id}", f"ADDCOST#{cost_id}", updates)

    watch = get_item(f"W#{watch_id}", "META")
    all_costs = query_pk(f"W#{watch_id}", "ADDCOST#")
    presale, additional = split_addcost_totals(all_costs)
    landed = recalc_landed(watch)
    cost_basis = total_cost_basis(landed, presale)

    merged = {**watch, "total_landed_cost_usd": landed, "total_additional_costs_usd": additional}
    net_profit = recalc_profit(merged, load_config())

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

    return api_response(200, {
        "cost_id": cost_id,
        "total_additional_costs_usd": additional,
        "total_presale_costs_usd": presale,
        "total_landed_cost_usd": landed,
        "total_cost_basis_usd": cost_basis,
    })
