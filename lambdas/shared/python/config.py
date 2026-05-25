import os
import json
import boto3

_config_cache = None


def load_config(force_reload=False) -> dict:
    global _config_cache
    if _config_cache and not force_reload:
        return _config_cache

    s3 = boto3.client("s3")
    bucket = os.environ["CONFIG_BUCKET"]
    key = os.environ.get("CONFIG_KEY", "config.json")

    resp = s3.get_object(Bucket=bucket, Key=key)
    body = resp["Body"].read().decode("utf-8")

    raw = json.loads(body)

    # Flatten: top-level keys are strings; caliber_hints stays as a nested dict.
    # Keys starting with "_" are comments — skip them.
    cfg = {}
    for k, v in raw.items():
        if k.startswith("_"):
            continue
        cfg[k] = v  # v may be a string or a dict (caliber_hints)

    _config_cache = cfg
    return cfg
