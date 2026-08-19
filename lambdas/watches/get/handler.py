import os
import boto3
from db import get_item, query_pk, api_response


def handler(event, context):
    watch_id = event["pathParameters"]["id"]
    watch = get_item(f"W#{watch_id}", "META")
    if not watch:
        return api_response(404, {"error": "Watch not found"})

    transitions = query_pk(f"W#{watch_id}", "STAGE#")
    costs = query_pk(f"W#{watch_id}", "ADDCOST#")

    watch["transitions"] = transitions
    watch["additional_costs"] = costs

    thumb_key = watch.get("thumbnail_key", "")
    photos_bucket = os.environ.get("PHOTOS_BUCKET", "")
    watch["thumbnail_url"] = None
    if thumb_key and photos_bucket:
        try:
            watch["thumbnail_url"] = boto3.client("s3").generate_presigned_url(
                "get_object",
                Params={"Bucket": photos_bucket, "Key": thumb_key},
                ExpiresIn=86400,
            )
        except Exception:
            pass

    return api_response(200, watch)
