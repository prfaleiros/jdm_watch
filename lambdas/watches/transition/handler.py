import json
from models import stage_transition_item, VALID_STATUSES, now_iso
from db import get_item, put_item, update_fields, api_response


def handler(event, context):
    watch_id = event["pathParameters"]["id"]
    body = json.loads(event.get("body", "{}"))

    watch = get_item(f"W#{watch_id}", "META")
    if not watch:
        return api_response(404, {"error": "Watch not found"})

    to_status = body.get("to_status")
    if to_status not in VALID_STATUSES:
        return api_response(400, {"error": f"Invalid status. Valid: {VALID_STATUSES}"})

    from_status = watch["current_status"]
    hours = body.get("hours_spent", 0)
    notes = body.get("notes", "")
    event_date = body.get("event_date")  # Optional YYYY-MM-DD override for display

    transition = stage_transition_item(watch_id, {
        "from_status": from_status,
        "to_status": to_status,
        "hours_spent": hours,
        "notes": notes,
        "event_date": event_date,
    })
    put_item(transition)

    # Update watch META
    new_labor = (watch.get("total_labor_hours") or 0) + hours
    updates = {
        "current_status": to_status,
        "total_labor_hours": new_labor,
        "updated_at": now_iso(),
        "GSI1PK": f"STATUS#{to_status}",
    }
    update_fields(f"W#{watch_id}", "META", updates)

    return api_response(200, {
        "watch_id": watch_id,
        "from": from_status,
        "to": to_status,
        "hours_logged": hours,
        "total_labor_hours": new_labor,
    })
