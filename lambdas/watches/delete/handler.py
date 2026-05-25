from db import get_item, query_pk, batch_delete, api_response


def handler(event, context):
    watch_id = event["pathParameters"]["id"]

    if not get_item(f"W#{watch_id}", "META"):
        return api_response(404, {"error": "Watch not found"})

    # Fetch every DynamoDB item belonging to this watch (META + STAGE + ADDCOST)
    all_items = query_pk(f"W#{watch_id}")
    batch_delete([{"PK": item["PK"], "SK": item["SK"]} for item in all_items])

    # Note: S3 photos are left in place — delete via console if needed.
    return api_response(200, {
        "watch_id": watch_id,
        "deleted_items": len(all_items),
    })
