from db import get_item, query_pk, api_response


def handler(event, context):
    watch_id = event["pathParameters"]["id"]
    watch = get_item(f"W#{watch_id}", "META")
    if not watch:
        return api_response(404, {"error": "Watch not found"})

    transitions = query_pk(f"W#{watch_id}", "STAGE#")
    costs = query_pk(f"W#{watch_id}", "ADDCOST#")

    watch["transitions"] = transitions
    watch["additional_costs"] = costs
    return api_response(200, watch)
