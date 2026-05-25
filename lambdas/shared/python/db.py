import os
import boto3
from boto3.dynamodb.conditions import Key
from decimal import Decimal
import json

_table = None


def _convert_floats(obj):
    """Convert floats to Decimal for DynamoDB, strip None values."""
    if isinstance(obj, dict):
        return {k: _convert_floats(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [_convert_floats(i) for i in obj]
    if isinstance(obj, float):
        return Decimal(str(obj))
    return obj


def _convert_decimals(obj):
    """Convert Decimals back to float for JSON serialization."""
    if isinstance(obj, dict):
        return {k: _convert_decimals(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_convert_decimals(i) for i in obj]
    if isinstance(obj, Decimal):
        if obj % 1 == 0:
            return int(obj)
        return float(obj)
    return obj


def get_table():
    global _table
    if _table is None:
        dynamodb = boto3.resource("dynamodb")
        _table = dynamodb.Table(os.environ["TABLE_NAME"])
    return _table


def put_item(item: dict):
    get_table().put_item(Item=_convert_floats(item))


def get_item(pk: str, sk: str) -> dict | None:
    resp = get_table().get_item(Key={"PK": pk, "SK": sk})
    item = resp.get("Item")
    return _convert_decimals(item) if item else None


def query_pk(pk: str, sk_prefix: str = None) -> list:
    kwargs = {"KeyConditionExpression": Key("PK").eq(pk)}
    if sk_prefix:
        kwargs["KeyConditionExpression"] &= Key("SK").begins_with(sk_prefix)
    resp = get_table().query(**kwargs)
    return [_convert_decimals(i) for i in resp.get("Items", [])]


def query_gsi(index_name: str, pk_val: str) -> list:
    resp = get_table().query(
        IndexName=index_name,
        KeyConditionExpression=Key("GSI1PK").eq(pk_val),
    )
    return [_convert_decimals(i) for i in resp.get("Items", [])]


def update_fields(pk: str, sk: str, fields: dict):
    clean = _convert_floats(fields)
    expr_parts = []
    names = {}
    values = {}
    for i, (k, v) in enumerate(clean.items()):
        token = f"#f{i}"
        val_token = f":v{i}"
        expr_parts.append(f"{token} = {val_token}")
        names[token] = k
        values[val_token] = v
    get_table().update_item(
        Key={"PK": pk, "SK": sk},
        UpdateExpression="SET " + ", ".join(expr_parts),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )


def delete_item(pk: str, sk: str):
    get_table().delete_item(Key={"PK": pk, "SK": sk})


def batch_delete(items: list):
    """Delete multiple items. items: list of {"PK": ..., "SK": ...}."""
    if not items:
        return
    with get_table().batch_writer() as batch:
        for item in items:
            batch.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})


def api_response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body, default=str),
    }
