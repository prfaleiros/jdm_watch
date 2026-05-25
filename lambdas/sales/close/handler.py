import json
from models import stage_transition_item, additional_cost_item, now_iso
from db import get_item, put_item, update_fields, api_response
from config import load_config


def _recalc_landed(watch: dict, ad_delta: float) -> float:
    auction = float(watch.get("auction_price_usd") or 0)
    customs = float(watch.get("customs_duty_usd") or 0)
    intl = float(watch.get("intl_shipping_usd") or 0)
    existing_additional = float(watch.get("total_additional_costs_usd") or 0)
    buyee_jpy = (
        float(watch.get("buyee_platform_jpy") or 0)
        + float(watch.get("buyee_inspection_jpy") or 0)
        + float(watch.get("domestic_shipping_jpy") or 0)
    )
    jpy_rate = 0
    if watch.get("auction_price_jpy") and watch.get("auction_price_usd"):
        jpy_rate = float(watch["auction_price_usd"]) / float(watch["auction_price_jpy"])
    buyee_usd = buyee_jpy * jpy_rate if jpy_rate else 0
    return round(auction + customs + intl + buyee_usd + existing_additional + ad_delta, 2)


def handler(event, context):
    watch_id = event["pathParameters"]["id"]
    body = json.loads(event.get("body", "{}"))

    watch = get_item(f"W#{watch_id}", "META")
    if not watch:
        return api_response(404, {"error": "Watch not found"})

    sale_price = body.get("sale_price_usd")
    if not sale_price:
        return api_response(400, {"error": "sale_price_usd is required"})

    sale_price = float(sale_price)
    cfg = load_config()

    sale_platform  = body.get("sale_platform", "ebay")
    sale_date      = body.get("sale_date", now_iso()[:10])
    event_date     = body.get("event_date", sale_date)
    shipping_cost  = float(body.get("shipping_cost_usd", cfg.get("shipping_to_buyer", "6")))
    hours_spent    = float(body.get("hours_spent", 0))
    notes          = body.get("notes", "")
    ad_spend       = float(body.get("ad_spend_usd", 0))
    ad_notes       = body.get("ad_notes", "Ad spend")

    # Platform fees: always entered manually — eBay applies 15% to (price + buyer's sales tax),
    # which is unknown until the transaction settles. No point estimating.
    platform_fees = float(body.get("platform_fees_usd", 0))

    # ── Step 1: Record ad spend as ADDCOST ───────────────────────────────────
    ad_delta = 0.0
    if ad_spend > 0:
        put_item(additional_cost_item(watch_id, {
            "amount_usd": ad_spend,
            "category": "advertising",
            "notes": ad_notes,
        }))
        ad_delta = ad_spend

    # ── Step 2: Log stage transition ─────────────────────────────────────────
    from_status = watch.get("current_status", "listed")
    put_item(stage_transition_item(watch_id, {
        "from_status": from_status,
        "to_status": "sold",
        "hours_spent": hours_spent,
        "notes": notes,
        "event_date": event_date,
    }))

    # ── Step 3: Recalculate and update META ───────────────────────────────────
    new_labor_hours = float(watch.get("total_labor_hours") or 0) + hours_spent
    new_additional  = float(watch.get("total_additional_costs_usd") or 0) + ad_delta
    new_landed      = _recalc_landed(watch, ad_delta)
    labor_rate      = float(cfg.get("labor_rate", "1"))
    net_profit      = round(
        sale_price - platform_fees - shipping_cost - new_landed - (new_labor_hours * labor_rate),
        2,
    )

    update_fields(f"W#{watch_id}", "META", {
        "current_status":              "sold",
        "GSI1PK":                      "STATUS#sold",
        "GSI1SK":                      f"W#{watch_id}",
        "sale_price_usd":              sale_price,
        "sale_platform":               sale_platform,
        "sale_date":                   sale_date,
        "shipping_cost_usd":           shipping_cost,
        "platform_fees_usd":           platform_fees,
        "total_labor_hours":           new_labor_hours,
        "total_additional_costs_usd":  new_additional,
        "total_landed_cost_usd":       new_landed,
        "net_profit_usd":              net_profit,
        "updated_at":                  now_iso(),
    })

    return api_response(200, {
        "watch_id":              watch_id,
        "from_status":           from_status,
        "sale_price_usd":        sale_price,
        "platform_fees_usd":     platform_fees,
        "shipping_cost_usd":     shipping_cost,
        "total_landed_cost_usd": new_landed,
        "net_profit_usd":        net_profit,
        "message":               "Sale closed.",
    })
