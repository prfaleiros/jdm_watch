#!/usr/bin/env python3
"""
Seed DynamoDB with existing inventory from CSV.

Usage:
  python seed.py --file inventory.csv --table WatchBusiness [--dry-run]

CSV columns (header row required):
  brand, collection, reference, jdm_model, serial,
  diameter_mm, lug_to_lug_mm, thickness_mm, lug_width_mm,
  case_material, solar, radio_sync, color,
  auction_price_jpy, auction_price_usd,
  buyee_platform_jpy, buyee_inspection_jpy, domestic_shipping_jpy,
  customs_duty_usd, intl_shipping_usd,
  current_status, is_personal, notes
"""
import argparse
import csv
import json
import sys
import boto3
from decimal import Decimal

sys.path.insert(0, "../lambdas/shared/python")
from models import watch_item, stage_transition_item


BOOL_FIELDS = {"solar", "radio_sync", "is_personal"}
FLOAT_FIELDS = {
    "diameter_mm", "lug_to_lug_mm", "thickness_mm", "lug_width_mm",
    "auction_price_jpy", "auction_price_usd",
    "buyee_platform_jpy", "buyee_inspection_jpy", "domestic_shipping_jpy",
    "customs_duty_usd", "intl_shipping_usd",
}


def parse_bool(val: str) -> bool:
    return val.strip().lower() in ("true", "yes", "y", "1")


def parse_float(val: str):
    val = val.strip()
    if not val:
        return None
    try:
        return float(val)
    except ValueError:
        return None


def convert_floats_to_decimal(obj):
    if isinstance(obj, dict):
        return {k: convert_floats_to_decimal(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [convert_floats_to_decimal(i) for i in obj]
    if isinstance(obj, float):
        return Decimal(str(obj))
    return obj


def main():
    parser = argparse.ArgumentParser(description="Seed watch inventory")
    parser.add_argument("--file", required=True, help="CSV file path")
    parser.add_argument("--table", default="WatchBusiness", help="DynamoDB table name")
    parser.add_argument("--dry-run", action="store_true", help="Print items without writing")
    args = parser.parse_args()

    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(args.table)

    with open(args.file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        count = 0
        for row in reader:
            data = {}
            for k, v in row.items():
                k = k.strip()
                v = v.strip() if v else ""
                if k in BOOL_FIELDS:
                    data[k] = parse_bool(v)
                elif k in FLOAT_FIELDS:
                    data[k] = parse_float(v)
                elif v:
                    data[k] = v
            item = watch_item(data)
            transition = stage_transition_item(item["watch_id"], {
                "from_status": "",
                "to_status": item["current_status"],
                "hours_spent": 0,
                "notes": "Seeded from CSV",
            })

            if args.dry_run:
                print(json.dumps({k: v for k, v in item.items() if v is not None}, indent=2, default=str))
                print("---")
            else:
                table.put_item(Item=convert_floats_to_decimal(item))
                table.put_item(Item=convert_floats_to_decimal(transition))
                print(f"  Created: {item['watch_id']} - {item['brand']} {item['reference']}")
            count += 1

    action = "Would create" if args.dry_run else "Created"
    print(f"\n{action} {count} watches.")


if __name__ == "__main__":
    main()
