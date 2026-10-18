#!/usr/bin/env python3
"""
One-off migration: backfill `listed_date` on watches from their STAGE# transition history.

Financials' "days to sell" used to be sale_date - created_at (record age). It now uses
listed_date, which the transition handler stamps on the first move to "listed". This script
derives it for existing watches from the earliest transition into "listed" (using the
user-supplied event_date, falling back to the insertion timestamp).

Watches that are listed/sold/shipped but have NO transition into "listed" are reported, not
guessed at — fix those by hand via the Watch page's Admin tab (listed_date is patchable).
Watches that already have a listed_date are left alone.

Usage:
  python migrate_listed_date.py --table WatchBusiness          # dry run, prints a report only
  python migrate_listed_date.py --table WatchBusiness --apply  # actually writes the updates
"""
import argparse
import boto3
from boto3.dynamodb.conditions import Key, Attr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    table = boto3.resource("dynamodb").Table(args.table)
    resp = table.scan(FilterExpression=Attr("entity_type").eq("WATCH"))
    watches = resp["Items"]
    while "LastEvaluatedKey" in resp:
        resp = table.scan(FilterExpression=Attr("entity_type").eq("WATCH"),
                          ExclusiveStartKey=resp["LastEvaluatedKey"])
        watches += resp["Items"]

    updates, unresolved = [], []
    for w in watches:
        if w.get("listed_date"):
            continue
        wid = w["watch_id"]
        stages = table.query(
            KeyConditionExpression=Key("PK").eq(f"W#{wid}") & Key("SK").begins_with("STAGE#")
        )["Items"]
        listed = sorted(
            (s.get("event_date") or s["timestamp"][:10])
            for s in stages if s.get("to_status") == "listed"
        )
        if listed:
            updates.append((wid, listed[0], w))
        elif w.get("current_status") in ("listed", "sold", "shipped"):
            unresolved.append(w)

    print(f"{len(updates)} watch(es) to backfill:")
    for wid, d, w in updates:
        print(f"  {wid}  {w.get('brand','')} {w.get('reference','')}  -> listed_date {d}")
    print(f"\n{len(unresolved)} listed/sold watch(es) with no 'listed' transition (set by hand):")
    for w in unresolved:
        print(f"  {w['watch_id']}  {w.get('brand','')} {w.get('reference','')}  "
              f"[{w.get('current_status')}]  sale_date={w.get('sale_date')}")

    if not args.apply:
        print("\nDry run — pass --apply to write.")
        return
    for wid, d, _ in updates:
        table.update_item(
            Key={"PK": f"W#{wid}", "SK": "META"},
            UpdateExpression="SET listed_date = :d",
            ExpressionAttributeValues={":d": d},
        )
    print(f"\nWrote listed_date on {len(updates)} watch(es).")


if __name__ == "__main__":
    main()
