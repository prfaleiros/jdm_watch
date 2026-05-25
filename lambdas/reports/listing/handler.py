import os
import boto3
from db import get_item, api_response
from config import load_config
from pricing import forward_price


def handler(event, context):
    watch_id = event["pathParameters"]["id"]
    watch = get_item(f"W#{watch_id}", "META")
    if not watch:
        return api_response(404, {"error": "Watch not found"})

    cfg = load_config()
    prices = forward_price(watch, cfg)

    # ── Identity fields ───────────────────────────────────────────────────────
    brand      = watch.get("brand", "")
    collection = watch.get("collection", "")
    jdm_model  = watch.get("jdm_model", "")
    reference  = watch.get("reference", "")
    material   = watch.get("case_material", "")
    color      = watch.get("color", "")
    diameter   = watch.get("diameter_mm", "")

    # ── Positive-only feature tokens for the title ────────────────────────────
    # Only assert features the watch actually has; never negate absent ones.
    feature_tokens = []
    if watch.get("solar"):
        feature_tokens.append("Solar")
    if watch.get("radio_sync"):
        feature_tokens.append("Radio")
    if material:
        feature_tokens.append(material)

    features_str = " ".join(feature_tokens)
    title_parts  = [brand, collection, jdm_model, "JDM", features_str, color, "Dial"]
    if diameter:
        title_parts.append(f"{diameter}mm")
    title_parts.append("– US Seller")
    title = " ".join(p for p in title_parts if p).strip()
    title = " ".join(title.split())  # collapse any double spaces

    # ── Specs block — factual, no negatives ──────────────────────────────────
    def _mm(val):
        return f"{val}mm" if val else None

    # Movement type: derive from flags if not explicitly set
    movement_type = watch.get("movement_type", "")
    if not movement_type:
        if watch.get("solar") and watch.get("radio_sync"):
            movement_type = "Solar Radio-Controlled Quartz"
        elif watch.get("solar"):
            movement_type = "Solar Quartz"
        elif watch.get("radio_sync"):
            movement_type = "Radio-Controlled Quartz"

    jewel_count = watch.get("jewel_count")
    jewels_str  = f"{jewel_count}J" if jewel_count is not None and int(jewel_count) > 0 else None

    specs_raw = {
        "Brand":            brand,
        "Collection":       collection,
        "Reference":        reference,
        "JDM Model":        jdm_model,
        "Movement":         movement_type,
        "Jewels":           jewels_str,
        "Case Material":    material,
        "Crystal":          watch.get("crystal_type"),
        "Bracelet":         watch.get("bracelet_material"),
        "Dial Color":       color,
        "Diameter":         _mm(diameter),
        "Lug to Lug":       _mm(watch.get("lug_to_lug_mm")),
        "Thickness":        _mm(watch.get("thickness_mm")),
        "Lug Width":        _mm(watch.get("lug_width_mm")),
        "Water Resistance": watch.get("water_resistance"),
        "Power Reserve":    watch.get("power_reserve"),
        # Only include Radio Controlled when True
        **({"Radio Controlled": "Yes"} if watch.get("radio_sync") else {}),
    }

    # Strip empty / None / bare-unit strings
    specs = {k: v for k, v in specs_raw.items() if v and v not in ("mm", "0mm")}

    # ── Description ──────────────────────────────────────────────────────────
    desc_lines = [
        title,
        "",
        "This is a Japan Domestic Market (JDM) piece — not available through US retail channels.",
        "",
        "SPECIFICATIONS:",
    ]
    for k, v in specs.items():
        desc_lines.append(f"• {k}: {v}")

    # Feature pitch (free-text field, generated and saved via the app)
    pitch = watch.get("feature_pitch", "").strip()
    if pitch:
        desc_lines += ["", pitch]

    desc_lines += [
        "",
        "CONDITION:",
        f"Pre-owned. {watch.get('notes', '')}".strip(),
        "",
        "WHAT'S INCLUDED:",
        "• Watch only (no box or papers — typical for JDM sourcing)",
        "",
        "SHIPPING:",
        "• Free USPS Ground Advantage shipping within the US",
        "• Ships within 1 business day of payment",
        "",
        "RETURNS:",
        "• 14-day returns accepted. Buyer pays return shipping.",
    ]

    # ── Photo presigned URLs ──────────────────────────────────────────────────
    photos_bucket = os.environ.get("PHOTOS_BUCKET", "")
    s3 = boto3.client("s3")
    photo_urls = []
    if photos_bucket:
        try:
            resp = s3.list_objects_v2(Bucket=photos_bucket, Prefix=f"photos/{watch_id}/")
            for obj in resp.get("Contents", []):
                url = s3.generate_presigned_url("get_object", Params={
                    "Bucket": photos_bucket, "Key": obj["Key"]
                }, ExpiresIn=86400)
                photo_urls.append({"key": obj["Key"], "url": url})
        except Exception:
            pass

    return api_response(200, {
        "watch_id":    watch_id,
        "title":       title,
        "description": "\n".join(desc_lines),
        "specs":       specs,
        "pricing":     prices,
        "photos":      photo_urls,
        "feature_pitch": pitch,
    })
