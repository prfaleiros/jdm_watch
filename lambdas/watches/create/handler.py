import json
from models import watch_item, stage_transition_item
from db import put_item, api_response
from costs import recalc_landed, total_cost_basis


def handler(event, context):
    body = json.loads(event.get("body", "{}"))
    item = watch_item(body)
    item["total_landed_cost_usd"] = recalc_landed(item)
    # No ADDCOST records yet at creation, so pre-sale costs are 0 and cost basis == landed.
    item["total_cost_basis_usd"] = total_cost_basis(item["total_landed_cost_usd"], 0)
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
