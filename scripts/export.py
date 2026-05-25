#!/usr/bin/env python3
"""
Export watch inventory from DynamoDB to CSV.

Usage:
  python export.py --table WatchBusiness --output watches.csv [--status listed]
"""
import argparse
import csv
import boto3
from decimal import Decimal

EXPORT_FIELDS = [
    "watch_id", "brand", "collection", "reference", "jdm_model", "serial",
    "diameter_mm", "lug_to_lug_mm", "thickness_mm", "lug_width_mm",
    "case_material", "solar", "radio_sync", "color",
    "auction_price_jpy", "auction_price_usd",
    "buyee_platform_jpy", "buyee_inspection_jpy", "domestic_shipping_jpy",
    "customs_duty_usd", "intl_shipping_usd",
    "total_additional_costs_usd", "total_labor_hours", "total_landed_cost_usd",
    "sale_price_usd", "sale_platform", "sale_date",
    "shipping_cost_usd", "platform_fees_usd", "net_profit_usd",
    "is_personal", "current_status", "notes",
    "created_at", "updated_at",
]


def decimal_default(val):
    if isinstance(val, Decimal):
        return float(val) if val % 1 else int(val)
    return val


def main():
    parser = argparse.ArgumentParser(description="Export watches to CSV")
    parser.add_argument("--table", default="WatchBusiness")
    parser.add_argument("--output", default="watches_export.csv")
    parser.add_argument("--status", help="Filter by status (optional)")
    args = parser.parse_args()

    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(args.table)

    if args.status:
        resp = table.query(
            IndexName="GSI1",
            KeyConditionExpression=boto3.dynamodb.conditions.Key("GSI1PK").eq(f"STATUS#{args.status}"),
        )
        items = resp.get("Items", [])
    else:
        resp = table.scan(
            FilterExpression="entity_type = :et",
            ExpressionAttributeValues={":et": "WATCH"},
        )
        items = resp.get("Items", [])

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=EXPORT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for item in items:
            row = {k: decimal_default(item.get(k, "")) for k in EXPORT_FIELDS}
            writer.writerow(row)

    print(f"Exported {len(items)} watches to {args.output}")


if __name__ == "__main__":
    main()
