from db import get_item, api_response
from config import load_config
from pricing import forward_price


def handler(event, context):
    watch_id = event["pathParameters"]["id"]
    watch = get_item(f"W#{watch_id}", "META")
    if not watch:
        return api_response(404, {"error": "Watch not found"})

    cfg = load_config()
    result = forward_price(watch, cfg)
    result["watch_id"] = watch_id
    result["reference"] = watch.get("reference", "")
    result["jdm_model"] = watch.get("jdm_model", "")
    return api_response(200, result)
