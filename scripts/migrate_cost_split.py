#!/usr/bin/env python3
"""
One-off migration: split total_landed_cost_usd into pure acquisition cost +
total_presale_costs_usd + total_cost_basis_usd, for watches created before the cost-model
split (see CLAUDE.md / lambdas/shared/python/costs.py for the full explanation).

Does NOT touch net_profit_usd, total_additional_costs_usd, or any sale field — those are
unchanged by the split (see the math in the plan/commit message). Only landed/presale/
cost_basis are recomputed.

Deterministic reclassification: ADDCOST items with category in {part, consumable, tool} are
pre-sale. Everything else (shipping, advertising, other) is left out of the pre-sale bucket,
same as today's implicit behavior — NOT silently reclassified either way if ambiguous. Any
watch with a "shipping" or "other" category ADDCOST is flagged in the "review these" list for
manual eyeballing via the Watch page's Admin tab.

Usage:
  python migrate_cost_split.py --table WatchBusiness          # dry run, prints a report only
  python migrate_cost_split.py --table WatchBusiness --apply  # actually writes the updates
"""
import argparse
import boto3
from boto3.dynamodb.conditions import Key
from decimal import Decimal

PRESALE_CATEGORIES = {"part", "consumable", "tool"}
REVIEW_CATEGORIES = {"shipping", "other"}


def _f(val) -> float:
    if val is None:
        return 0.0
    if isinstance(val, Decimal):
        return float(val)
    return float(val)


def recalc_landed(watch: dict) -> float:
    auction = _f(watch.get("auction_price_usd"))
    customs = _f(watch.get("customs_duty_usd"))
    intl = _f(watch.get("intl_shipping_usd"))
    buyee_jpy = (
        _f(watch.get("buyee_platform_jpy"))
        + _f(watch.get("buyee_inspection_jpy"))
        + _f(watch.get("domestic_shipping_jpy"))
    )
    jpy_rate = 0.0
    if watch.get("auction_price_jpy") and watch.get("auction_price_usd"):
        jpy_rate = _f(watch["auction_price_usd"]) / _f(watch["auction_price_jpy"])
    buyee_usd = buyee_jpy * jpy_rate if jpy_rate else 0.0
    return round(auction + customs + intl + buyee_usd, 2)


def main():
    parser = argparse.ArgumentParser(description="Migrate landed cost -> landed + presale + cost_basis")
    parser.add_argument("--table", default="WatchBusiness")
    parser.add_argument("--apply", action="store_true", help="Actually write updates (default: dry run)")
    args = parser.parse_args()

    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(args.table)

    resp = table.scan(
        FilterExpression="entity_type = :et",
        ExpressionAttributeValues={":et": "WATCH"},
    )
    watches = resp.get("Items", [])

    review_watches = []
    changed = 0

    print(f"{'Watch':<10} {'Ref':<16} {'Old Landed':>12} {'New Landed':>12} {'Presale':>10} {'Cost Basis':>12}")
    print("-" * 76)

    for watch in watches:
        watch_id = watch["watch_id"]
        addcost_resp = table.query(
            KeyConditionExpression=Key("PK").eq(f"W#{watch_id}") & Key("SK").begins_with("ADDCOST#"),
        )
        addcosts = addcost_resp.get("Items", [])

        presale = round(sum(_f(c.get("amount_usd")) for c in addcosts if c.get("category") in PRESALE_CATEGORIES), 2)
        new_landed = recalc_landed(watch)
        cost_basis = round(new_landed + presale, 2)
        old_landed = _f(watch.get("total_landed_cost_usd"))

        ref = watch.get("reference", "")[:16]
        print(f"{watch_id:<10} {ref:<16} {old_landed:>12.2f} {new_landed:>12.2f} {presale:>10.2f} {cost_basis:>12.2f}")

        if any(c.get("category") in REVIEW_CATEGORIES for c in addcosts):
            review_watches.append(watch_id)

        if args.apply:
            table.update_item(
                Key={"PK": f"W#{watch_id}", "SK": "META"},
                UpdateExpression="SET total_landed_cost_usd = :landed, "
                                 "total_presale_costs_usd = :presale, "
                                 "total_cost_basis_usd = :basis",
                ExpressionAttributeValues={
                    ":landed": Decimal(str(new_landed)),
                    ":presale": Decimal(str(presale)),
                    ":basis": Decimal(str(cost_basis)),
                },
            )
        changed += 1

    print("-" * 76)
    print(f"{'APPLIED' if args.apply else 'DRY RUN'}: {changed} watch(es) processed.")

    if review_watches:
        print(f"\nReview these {len(review_watches)} watch(es) — they have a 'shipping' or "
              f"'other' category cost whose pre-sale timing wasn't auto-classified either way:")
        for wid in review_watches:
            print(f"  {wid}")
        print("Check via the Watch page's Admin tab and adjust total_presale_costs_usd's "
              "inputs (i.e. that ADDCOST record's category) if it should count as pre-sale.")

    if not args.apply:
        print("\nThis was a dry run — nothing was written. Re-run with --apply to commit these changes.")


if __name__ == "__main__":
    main()
