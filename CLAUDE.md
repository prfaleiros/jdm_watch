# JDM Watch Business — Project Context

Personal side-hustle app for Paulo: buys Japanese Domestic Market (JDM) watches on Buyee
(Japanese auction aggregator), ships them to the US, refurbishes/inspects on the bench, then
sells on eBay and Reddit (r/Watchexchange). Focus: solar-powered, radio-controlled (atomic
sync), titanium-case pieces hard to find in the US market.

This replaced a spreadsheet. Goals: cost visibility, automated pricing tiers, a max-bid
calculator (no more Saturday-morning auction guessing), lifecycle tracking, S3 as the source
of truth for photos, and generated eBay listing copy from structured data.

This is a side hustle, not a startup — favor low-friction fixes over new services/patterns.
Don't push the LLC/sales-tax-permit angle; Paulo knows and is deliberately deferring it.

## Architecture

- **Backend:** AWS CDK v2 (Python) — `cdk/stacks/watch_stack.py`. Lambda (Python 3.12) +
  DynamoDB single-table design + API Gateway REST with API-key auth.
- **Frontend:** Streamlit multi-page app in `streamlit_app/`, deployed on Streamlit Community
  Cloud (public repo, viewer auth restricted to Paulo's email via Google/GitHub login
  allowlist). No longer run locally — mobile access via the Cloud URL is the primary way
  Paulo uses this app now. Auto-redeploys on push to `main`.
- **Pricing engine:** `lambdas/shared/python/pricing.py` + config loaded from
  `lambdas/shared/python/config.py`, which reads `config/config.json` from an S3 config
  bucket (cached in Lambda memory — see Known Gotchas). `config/fees.csv` is legacy/dead —
  nothing reads it since 2026-05-13; don't resurrect it.
- **Photos:** S3, presigned PUT for upload / GET for display (24h TTL). Any Lambda
  generating presigned GET URLs needs `photos_bucket.grant_read(...)` in CDK.

## Pricing model (as of 2026-08)

Profit target per tier = `max(landed_cost × roi_pct, min_profit_usd)`.

- ROI targets: Fast 20%, Standard 33%, Patient 50% (`target_roi_pct_*` in config.json)
- Minimum profit floor: **$50** after all costs (`min_profit_usd`) — protects cheap pieces
  from being priced/bid below viable margin, and flags when ad spend eats too far into a
  thin-margin listing. Applied in both `forward_price()` (listing price) and
  `backward_max_bid()` (bid calculator — the more conservative of the ROI or floor constraint
  wins).
- eBay effective rate = FVF (15%) × (1 + sales tax blend 10%) + ad rate (default 5%,
  overridable per listing).
- Shipping: free USPS domestic (absorbed as $6 flat cost); international transitioning to a
  flat $40 rate via UPS Worldwide Expedited with limited destinations.
- Full fee/config schema lives in `config/config.json` — read it directly rather than
  trusting a stale summary.

## Streamlit pages

`app.py` (inventory/App tab) · `2_Watch.py` (detail: edit, photos incl. photo-first spec
lookup via Claude, costs, danger-zone delete) · `3_New_Watch.py` · `4_Shipment.py` ·
`5_Bid_Calculator.py` · `6_Import_Shipment.py` · `7_Offer_Analyzer.py` (real-time eBay offer
evaluation + counter suggestions, "listed" status only) · `8_eBay_Drafts.py` (generates an
eBay bulk-upload draft CSV from selected watches).

**Convention:** every watch-selection dropdown must show `[watch_id] Brand Collection
Reference` — duplicate references without the ID prefix caused repeated confusion bugs
across the App tab, Shipment page, and Offer Analyzer before this was standardized. Apply it
to any new dropdown from the start.

## Known gotchas

- **AWS profile:** always `export AWS_PROFILE=prfaleiros` before CDK/CLI commands — default
  profile has stale credentials.
- **Lambda config cache:** `config.py` caches `config.json` in memory; updates to the S3 file
  don't take effect until a cold start. Force one with
  `aws lambda update-function-configuration --function-name <name> --environment "Variables={CACHE_BUST=$(date +%s),...}"`
  or just redeploy.
- **Presigned S3 URLs (photos)** expire in 24h — relevant for the eBay Drafts CSV photo
  column; generate and use the same session.
- **`st.column_config.NumberColumn` format strings:** a leading `$` in the format string
  (e.g. `"$%.2f"`) is parsed as a POSIX positional sigil and breaks numeric sort — put the
  `$` in the column label instead, keep `format="%.2f"`.
- Don't guess AWS resource names (bucket names, etc.) in commands — look them up
  (`aws s3 ls --profile prfaleiros`) rather than fabricating a plausible pattern.

## Deferred / open TODOs

- Live eBay API push (currently CSV bulk-upload draft, still a manual Seller Hub step)
- Automated FX rate lookup for the bid calculator (currently manual entry)
- Bulk photo upload (currently one presigned URL at a time)
- `export.py` (DynamoDB → CSV) exists but untested end-to-end
- No delete/edit endpoint for lifecycle transitions — correcting a duplicate stage-transition
  currently means patching `total_labor_hours` directly, which is a hack
