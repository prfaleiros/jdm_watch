import json
from db import api_response
from config import load_config
from pricing import backward_max_bid


def handler(event, context):
    body = json.loads(event.get("body", "{}"))

    required = ["expected_sale_usd", "fx_rate"]
    missing = [f for f in required if f not in body]
    if missing:
        return api_response(400, {"error": f"Missing required fields: {missing}"})

    cfg = load_config()
    result = backward_max_bid(body, cfg)
    return api_response(200, result)
