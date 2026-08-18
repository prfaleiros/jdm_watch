import json
from models import ad_campaign_item, ad_campaign_watch_link
from db import put_item, api_response


def handler(event, context):
    body = json.loads(event.get("body", "{}"))

    if "total_cost_usd" not in body:
        return api_response(400, {"error": "total_cost_usd is required"})

    campaign = ad_campaign_item(body)
    put_item(campaign)

    watch_ids = body.get("watch_ids", [])
    for watch_id in watch_ids:
        put_item(ad_campaign_watch_link(campaign["campaign_id"], watch_id))

    return api_response(201, {
        "campaign_id": campaign["campaign_id"],
        "watches_linked": len(watch_ids),
    })
