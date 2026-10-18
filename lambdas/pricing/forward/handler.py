from db import get_item, api_response
from config import load_config
from pricing import forward_price

# Query-string overrides for what-if pricing (all optional): sales_tax_pct, ad_rate_pct,
# shipping_usd, min_profit_usd.
_OVERRIDE_KEYS = ("sales_tax_pct", "ad_rate_pct", "shipping_usd", "min_profit_usd")


def handler(event, context):
    watch_id = event["pathParameters"]["id"]
    watch = get_item(f"W#{watch_id}", "META")
    if not watch:
        return api_response(404, {"error": "Watch not found"})

    params = event.get("queryStringParameters") or {}
    overrides = {k: params[k] for k in _OVERRIDE_KEYS if k in params}

    cfg = load_config()
    try:
        result = forward_price(watch, cfg, overrides)
    except ArithmeticError:
        return api_response(400, {"error": "Invalid override value"})
    result["watch_id"] = watch_id
    result["reference"] = watch.get("reference", "")
    result["jdm_model"] = watch.get("jdm_model", "")
    return api_response(200, result)
