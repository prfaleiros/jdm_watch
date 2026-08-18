from db import query_gsi, api_response
from models import VALID_STATUSES
import boto3
import os


_INTERNAL_KEYS = {"PK", "SK", "GSI1PK", "GSI1SK", "entity_type"}


def handler(event, context):
    params = event.get("queryStringParameters") or {}
    status = params.get("status")
    full   = params.get("full") in ("1", "true")

    if status:
        if status not in VALID_STATUSES:
            return api_response(400, {"error": f"Invalid status. Valid: {VALID_STATUSES}"})
        items = query_gsi("GSI1", f"STATUS#{status}")
    else:
        # Scan all statuses — fine at this volume
        table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
        resp = table.scan(
            FilterExpression="entity_type = :et",
            ExpressionAttributeValues={":et": "WATCH"},
        )
        from db import _convert_decimals
        items = [_convert_decimals(i) for i in resp.get("Items", [])]

    photos_bucket = os.environ.get("PHOTOS_BUCKET", "")
    s3 = boto3.client("s3") if photos_bucket else None

    # Return summary, not full records
    summary = []
    for item in items:
        thumb_url = None
        thumb_key = item.get("thumbnail_key", "")
        if s3 and thumb_key:
            try:
                thumb_url = s3.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": photos_bucket, "Key": thumb_key},
                    ExpiresIn=86400,
                )
            except Exception:
                pass
        if full:
            row = {k: v for k, v in item.items() if k not in _INTERNAL_KEYS}
            row["thumbnail_key"] = thumb_key
            row["thumbnail_url"] = thumb_url
        else:
            row = {
                "watch_id": item.get("watch_id"),
                "brand": item.get("brand"),
                "collection": item.get("collection"),
                "reference": item.get("reference"),
                "jdm_model": item.get("jdm_model"),
                "current_status": item.get("current_status"),
                "total_landed_cost_usd": item.get("total_landed_cost_usd"),
                "total_cost_basis_usd": item.get("total_cost_basis_usd"),
                "is_personal": item.get("is_personal"),
                "thumbnail_key": thumb_key,
                "thumbnail_url": thumb_url,
            }
        summary.append(row)
    return api_response(200, {"count": len(summary), "watches": summary})
