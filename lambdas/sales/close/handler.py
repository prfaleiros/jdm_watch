import json
from models import stage_transition_item, additional_cost_item, now_iso
from db import get_item, put_item, query_pk, update_fields, api_response
from config import load_config
from costs import recalc_landed, split_addcost_totals, total_cost_basis, recalc_profit


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
    shipping_label_source = body.get("shipping_label_source", "platform")
    hours_spent    = float(body.get("hours_spent", 0))
    notes          = body.get("notes", "")
    ad_spend       = float(body.get("ad_spend_usd", 0))
    ad_notes       = body.get("ad_notes", "Ad spend")

    # Platform fees: always entered manually — eBay applies 15% to (price + buyer's sales tax),
    # which is unknown until the transaction settles. No point estimating.
    platform_fees = float(body.get("platform_fees_usd", 0))

    # ── Step 1: Record ad spend as ADDCOST (post-sale expense, not pre-sale) ──────
    if ad_spend > 0:
        put_item(additional_cost_item(watch_id, {
            "amount_usd": ad_spend,
            "category": "advertising",
            "notes": ad_notes,
        }))

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
    all_costs = query_pk(f"W#{watch_id}", "ADDCOST#")
    presale, additional = split_addcost_totals(all_costs)
    new_landed = recalc_landed(watch)
    cost_basis = total_cost_basis(new_landed, presale)

    merged = {
        **watch,
        "sale_price_usd": sale_price,
        "platform_fees_usd": platform_fees,
        "shipping_cost_usd": shipping_cost,
        "total_landed_cost_usd": new_landed,
        "total_additional_costs_usd": additional,
        "total_labor_hours": new_labor_hours,
    }
    net_profit = recalc_profit(merged, cfg)

    update_fields(f"W#{watch_id}", "META", {
        "current_status":              "sold",
        "GSI1PK":                      "STATUS#sold",
        "GSI1SK":                      f"W#{watch_id}",
        "sale_price_usd":              sale_price,
        "sale_platform":               sale_platform,
        "sale_date":                   sale_date,
        "shipping_cost_usd":           shipping_cost,
        "shipping_label_source":       shipping_label_source,
        "platform_fees_usd":           platform_fees,
        "total_labor_hours":           new_labor_hours,
        "total_additional_costs_usd":  additional,
        "total_presale_costs_usd":     presale,
        "total_landed_cost_usd":       new_landed,
        "total_cost_basis_usd":        cost_basis,
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
        "total_cost_basis_usd":  cost_basis,
        "net_profit_usd":        net_profit,
        "message":               "Sale closed.",
    })
