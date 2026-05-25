import uuid
from datetime import datetime, timezone

VALID_STATUSES = [
    "watching", "bid_placed", "won", "in_transit_jp", "at_buyee",
    "in_transit_us", "received", "on_bench", "ready_to_list",
    "listed", "sold", "shipped",
]


def new_id():
    return str(uuid.uuid4())[:8]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def watch_item(data: dict) -> dict:
    watch_id = data.get("watch_id") or new_id()
    ts = now_iso()
    return {
        "PK": f"W#{watch_id}",
        "SK": "META",
        "GSI1PK": f"STATUS#{data.get('current_status', 'watching')}",
        "GSI1SK": f"W#{watch_id}",
        "entity_type": "WATCH",
        "watch_id": watch_id,
        "created_at": ts,
        "updated_at": ts,
        # identity
        "brand": data.get("brand", ""),
        "collection": data.get("collection", ""),
        "reference": data.get("reference", ""),
        "jdm_model": data.get("jdm_model", ""),
        "serial": data.get("serial", ""),
        # specs
        "diameter_mm": data.get("diameter_mm"),
        "lug_to_lug_mm": data.get("lug_to_lug_mm"),
        "thickness_mm": data.get("thickness_mm"),
        "lug_width_mm": data.get("lug_width_mm"),
        "case_material": data.get("case_material", ""),
        "solar": data.get("solar", False),
        "radio_sync": data.get("radio_sync", False),
        "color": data.get("color", ""),
        "crystal_type": data.get("crystal_type", ""),
        "bracelet_material": data.get("bracelet_material", ""),
        "movement_type": data.get("movement_type", ""),
        "jewel_count": data.get("jewel_count"),
        "power_reserve": data.get("power_reserve", ""),
        "water_resistance": data.get("water_resistance", ""),
        # purchase costs
        "auction_price_jpy": data.get("auction_price_jpy"),
        "auction_price_usd": data.get("auction_price_usd"),
        "buyee_platform_jpy": data.get("buyee_platform_jpy", 500),
        "buyee_inspection_jpy": data.get("buyee_inspection_jpy", 500),
        "domestic_shipping_jpy": data.get("domestic_shipping_jpy", 900),
        "customs_duty_usd": data.get("customs_duty_usd"),
        "shipment_id": data.get("shipment_id"),
        # allocated (set by shipment allocation)
        "intl_shipping_usd": data.get("intl_shipping_usd"),
        # bench
        "total_labor_hours": data.get("total_labor_hours", 0),
        "total_additional_costs_usd": data.get("total_additional_costs_usd", 0),
        # derived
        "total_landed_cost_usd": data.get("total_landed_cost_usd"),
        # sale
        "sale_price_usd": data.get("sale_price_usd"),
        "sale_platform": data.get("sale_platform"),
        "sale_date": data.get("sale_date"),
        "shipping_cost_usd": data.get("shipping_cost_usd"),
        "platform_fees_usd": data.get("platform_fees_usd"),
        "net_profit_usd": data.get("net_profit_usd"),
        # flags
        "is_personal": data.get("is_personal", False),
        "current_status": data.get("current_status", "watching"),
        "notes": data.get("notes", ""),
        # media
        "thumbnail_key": data.get("thumbnail_key", ""),
    }


def stage_transition_item(watch_id: str, data: dict) -> dict:
    ts = now_iso()
    # event_date is the user-supplied date for display (e.g. backdated).
    # timestamp / SK always use insertion time for uniqueness and ordering.
    event_date = data.get("event_date") or ts[:10]
    return {
        "PK": f"W#{watch_id}",
        "SK": f"STAGE#{ts}",
        "entity_type": "STAGE_TRANSITION",
        "watch_id": watch_id,
        "from_status": data["from_status"],
        "to_status": data["to_status"],
        "hours_spent": data.get("hours_spent", 0),
        "notes": data.get("notes", ""),
        "event_date": event_date,
        "timestamp": ts,
    }


def additional_cost_item(watch_id: str, data: dict) -> dict:
    cost_id = new_id()
    return {
        "PK": f"W#{watch_id}",
        "SK": f"ADDCOST#{cost_id}",
        "entity_type": "ADDITIONAL_COST",
        "watch_id": watch_id,
        "cost_id": cost_id,
        "amount_usd": data["amount_usd"],
        "category": data.get("category", "other"),
        "notes": data.get("notes", ""),
        "date": data.get("date", now_iso()),
    }


def shipment_item(data: dict) -> dict:
    ship_id = data.get("shipment_id") or new_id()
    ts = now_iso()
    return {
        "PK": f"SHIP#{ship_id}",
        "SK": "META",
        "entity_type": "SHIPMENT",
        "shipment_id": ship_id,
        "created_at": ts,
        "total_cost_usd": data["total_cost_usd"],
        "total_cost_jpy": data.get("total_cost_jpy"),
        "weight_g": data.get("weight_g"),
        "dimensions": data.get("dimensions", ""),
        "carrier": data.get("carrier", "DHL"),
        "ship_date": data.get("ship_date", ""),
        "notes": data.get("notes", ""),
    }


def shipment_watch_link(shipment_id: str, watch_id: str, auction_price_jpy: float) -> dict:
    return {
        "PK": f"SHIP#{shipment_id}",
        "SK": f"W#{watch_id}",
        "entity_type": "SHIPMENT_WATCH",
        "shipment_id": shipment_id,
        "watch_id": watch_id,
        "auction_price_jpy": auction_price_jpy,
    }
