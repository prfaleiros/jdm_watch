import requests
import streamlit as st
from logger import log


def _headers():
    return {"x-api-key": st.secrets["API_KEY"], "Content-Type": "application/json"}


def _get_headers():
    return {"x-api-key": st.secrets["API_KEY"]}


def _url(path: str) -> str:
    base = st.secrets["API_URL"].rstrip("/")
    return f"{base}/{path.lstrip('/')}"


def _raise(r: requests.Response, context: str):
    """Log and raise on HTTP error."""
    try:
        r.raise_for_status()
    except requests.HTTPError as e:
        log.error("%s — HTTP %s: %s", context, r.status_code, r.text[:300])
        raise


def list_watches(status: str = None) -> list:
    params = {"status": status} if status else {}
    r = requests.get(_url("watches"), headers=_get_headers(), params=params)
    _raise(r, "list_watches")
    watches = r.json()["watches"]
    log.debug("list_watches → %d records", len(watches))
    return watches


def export_watches() -> list:
    """Full records for all watches — used for CSV export."""
    r = requests.get(_url("watches"), headers=_get_headers(), params={"full": "1"})
    _raise(r, "export_watches")
    watches = r.json()["watches"]
    log.debug("export_watches → %d records", len(watches))
    return watches


def get_watch(watch_id: str) -> dict:
    r = requests.get(_url(f"watches/{watch_id}"), headers=_get_headers())
    _raise(r, f"get_watch({watch_id})")
    log.debug("get_watch(%s) OK", watch_id)
    return r.json()


def create_watch(data: dict) -> dict:
    r = requests.post(_url("watches"), headers=_headers(), json=data)
    _raise(r, "create_watch")
    resp = r.json()
    log.info("create_watch → %s  ref=%s", resp.get("watch_id"), data.get("reference"))
    return resp


def update_watch(watch_id: str, data: dict) -> dict:
    r = requests.patch(_url(f"watches/{watch_id}"), headers=_headers(), json=data)
    _raise(r, f"update_watch({watch_id})")
    log.info("update_watch(%s) fields=%s", watch_id, list(data.keys()))
    return r.json()


def add_transition(watch_id: str, to_status: str, hours_spent: float, notes: str, event_date: str = None) -> dict:
    payload = {"to_status": to_status, "hours_spent": hours_spent, "notes": notes}
    if event_date:
        payload["event_date"] = event_date
    r = requests.post(_url(f"watches/{watch_id}/transitions"), headers=_headers(), json=payload)
    _raise(r, f"add_transition({watch_id}→{to_status})")
    log.info("add_transition(%s) → %s", watch_id, to_status)
    return r.json()


def add_cost(watch_id: str, amount_usd: float, category: str, notes: str) -> dict:
    payload = {"amount_usd": amount_usd, "category": category, "notes": notes}
    r = requests.post(_url(f"watches/{watch_id}/costs"), headers=_headers(), json=payload)
    _raise(r, f"add_cost({watch_id})")
    log.info("add_cost(%s) $%.2f [%s]", watch_id, amount_usd, category)
    return r.json()


def get_pricing(watch_id: str) -> dict:
    r = requests.get(_url(f"watches/{watch_id}/pricing"), headers=_get_headers())
    _raise(r, f"get_pricing({watch_id})")
    return r.json()


def get_listing_report(watch_id: str) -> dict:
    r = requests.get(_url(f"watches/{watch_id}/listing-report"), headers=_get_headers())
    _raise(r, f"get_listing_report({watch_id})")
    return r.json()


def get_upload_url(watch_id: str, filename: str) -> str:
    r = requests.get(
        _url(f"watches/{watch_id}/upload-url"),
        headers=_get_headers(),
        params={"filename": filename},
    )
    _raise(r, f"get_upload_url({watch_id})")
    return r.json()["upload_url"]


def upload_photo(presigned_url: str, file_bytes: bytes, content_type: str = "image/jpeg") -> None:
    r = requests.put(presigned_url, data=file_bytes, headers={"Content-Type": content_type})
    try:
        r.raise_for_status()
        log.info("upload_photo OK  size=%d  type=%s", len(file_bytes), content_type)
    except requests.HTTPError:
        log.error("upload_photo failed HTTP %s", r.status_code)
        raise


def close_sale(watch_id: str, payload: dict) -> dict:
    r = requests.post(_url(f"watches/{watch_id}/close"), headers=_headers(), json=payload)
    _raise(r, f"close_sale({watch_id})")
    resp = r.json()
    log.info("close_sale(%s) price=$%.2f profit=$%.2f",
             watch_id,
             payload.get("sale_price_usd", 0),
             resp.get("net_profit_usd", 0))
    return resp


def get_max_bid(payload: dict) -> dict:
    r = requests.post(_url("pricing/max-bid"), headers=_headers(), json=payload)
    _raise(r, "get_max_bid")
    return r.json()


def create_shipment(data: dict) -> dict:
    r = requests.post(_url("shipments"), headers=_headers(), json=data)
    _raise(r, "create_shipment")
    resp = r.json()
    log.info("create_shipment → %s", resp.get("shipment_id"))
    return resp


def delete_watch(watch_id: str) -> dict:
    r = requests.delete(_url(f"watches/{watch_id}"), headers=_get_headers())
    _raise(r, f"delete_watch({watch_id})")
    log.info("delete_watch(%s) OK", watch_id)
    return r.json()


def update_cost(watch_id: str, cost_id: str, data: dict) -> dict:
    r = requests.patch(_url(f"watches/{watch_id}/costs/{cost_id}"), headers=_headers(), json=data)
    _raise(r, f"update_cost({watch_id}/{cost_id})")
    log.info("update_cost(%s/%s) fields=%s", watch_id, cost_id, list(data.keys()))
    return r.json()


def delete_cost(watch_id: str, cost_id: str) -> dict:
    r = requests.delete(_url(f"watches/{watch_id}/costs/{cost_id}"), headers=_get_headers())
    _raise(r, f"delete_cost({watch_id}/{cost_id})")
    log.info("delete_cost(%s/%s) OK", watch_id, cost_id)
    return r.json()


def allocate_shipment(shipment_id: str) -> dict:
    r = requests.post(_url(f"shipments/{shipment_id}/allocate"), headers=_headers(), json={})
    _raise(r, f"allocate_shipment({shipment_id})")
    log.info("allocate_shipment(%s) OK", shipment_id)
    return r.json()
