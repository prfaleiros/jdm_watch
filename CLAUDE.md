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
  generating presigned GET URLs needs `photos_bucket.grant_read(...)` in CDK. Both
  `watches/list` and `watches/get` presign `thumbnail_url` from `thumbnail_key` — if a third
  read path for a watch record gets added, remember it too (`watches/get` had no
  `thumbnail_url` at all until 2026-08-19). `2_Watch.py` and `7_Offer_Analyzer.py`'s headers
  render it inline via `st.image(watch["thumbnail_url"])` when present.

## Pricing model (as of 2026-08)

Profit target per tier = `max(cost_basis × roi_pct, min_profit_usd)`.

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

## Cost model (as of 2026-08-18)

Three distinct buckets, split out for reconciling against real eBay/Buyee numbers — see
`lambdas/shared/python/costs.py` for the single source of truth (used by every handler that
touches these fields; don't reintroduce a local copy):

- **`total_landed_cost_usd`** — pure acquisition only: auction price + customs + intl
  shipping + Buyee fees. Does NOT include any `ADDCOST` amounts.
- **`buyee_fees_usd`** (as of 2026-08-19) — the *actual* USD card charge for Buyee
  platform+inspection+domestic-shipping fees combined, when known. Prefer this over deriving
  it from the auction's own JPY/USD rate (`costs.buyee_fees_usd()` handles the fallback) —
  Buyee fees are often charged in a separate transaction from the auction win, at a different
  FX rate, and that rate genuinely drifts (this business has seen ~150 to ~155 JPY/USD over
  time). Records without it show an estimated `~$X.XX` in the Watch page's Cost Breakdown;
  records with it show the real `$X.XX`. No migration was run to backfill old records — there
  was no better historical source to pull it from, so old records just keep the estimate.
- **`total_presale_costs_usd`** — sum of `ADDCOST` records categorized `part`/`consumable`/
  `tool` (bench/repair costs). `PRESALE_CATEGORIES` in `costs.py`. `shipping`/`advertising`/
  `other` categories are deliberately NOT auto-classified as pre-sale — timing is ambiguous,
  so they're left out unless corrected via the Watch page's Admin tab.
- **`total_cost_basis_usd`** — `landed + presale`, i.e. true all-in cost before a sale. This
  is what the pricing engine, Financials' "Capital Deployed", and the main inventory grid's
  "Landed ($)" column all actually use now (with a fallback to bare landed for pre-split
  records) — don't reintroduce bare `total_landed_cost_usd` as a display figure without
  checking whether cost_basis is what's actually wanted.
- `total_additional_costs_usd` — unchanged, still sum of *all* `ADDCOST` regardless of
  category. `net_profit_usd`'s formula is unchanged in substance (still subtracts landed +
  all-additional-costs once total); only the breakdown changed, not the bottom line — verified
  against all 24 real sold watches during the migration (totals matched exactly, $981.72).
- **`shipping_label_source`** (`"platform"` / `"external"`) — whether the shipping label came
  from the sales platform or an outside source (e.g. stamps.com). Captured alongside
  `shipping_cost_usd` at sale-close time or via Admin tab patch.
- **Ad campaigns** (`lambdas/campaigns/`) — a shared ad cost covering multiple watches at
  once (eBay Offsite Ads, Reddit promotion), modeled on the existing `Shipment` pattern but
  split **evenly** across linked watches rather than weighted by value. Allocating creates one
  `ADDCOST(category="advertising")` per watch via the existing `additional_cost_item()` — no
  new profit-calc path. UI: `streamlit_app/pages/10_Ad_Campaigns.py`.
- **Migration**: `scripts/migrate_cost_split.py` (dry-run by default, `--apply` to write) was
  run once against all 51 existing watches to backfill landed/presale/cost_basis. Deterministic
  reclassification only — no watch had an ambiguous `shipping`/`other` cost to flag for review.
- **Admin tab** (`2_Watch.py`, 7th tab) — a raw cost-field audit table + a generic "Quick
  Patch" (any `EDITABLE_FIELDS` value via the existing `PATCH /watches/{id}`) + a read-only
  full JSON dump. Built so Paulo stops hand-editing DynamoDB during reconciliation.

## Streamlit pages

`app.py` (inventory/App tab) · `2_Watch.py` (detail: edit, photos incl. photo-first spec
lookup via Claude, costs, danger-zone delete) · `3_New_Watch.py` · `4_Shipment.py` ·
`5_Bid_Calculator.py` · `6_Import_Shipment.py` · `7_Offer_Analyzer.py` (real-time eBay offer
evaluation + counter suggestions, "listed" status only) · `8_eBay_Drafts.py` (generates an
eBay bulk-upload draft CSV from selected watches) · `9_Financials.py` (Capital Deployed /
Realized P&L / Style Performance aggregated from existing watch records, plus "Ask Your
Data" — sends the full inventory+sales CSV to `claude-opus-4-5` for free-form analysis
instead of canned reports; excludes `is_personal` watches from all financial calcs).

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
- **Local dev venv drift:** the root `.venv` can fall behind `streamlit_app/requirements.txt`
  (e.g. `anthropic` was in requirements.txt but not actually installed locally). If a page
  that calls Claude throws `ModuleNotFoundError` locally, run
  `.venv/Scripts/pip.exe install -r streamlit_app/requirements.txt` before assuming it's a
  code bug — Streamlit Cloud installs fresh from requirements.txt every deploy, so this only
  bites local testing.
- `manage.sh` assumes `streamlit` is on PATH; in a fresh shell without the venv activated,
  call `.venv/Scripts/streamlit.exe` directly instead.
- Streamlit widgets that are set programmatically (e.g. an "example question" button filling
  a text area) need a stable `key=` bound to `st.session_state`, not just `value=`— without a
  key, the value is lost on the next rerun (e.g. when a separate submit button is clicked).
  This bit both `2_Watch.py`'s pitch text area (pre-existing, unfixed) and an early version of
  `9_Financials.py`'s "Ask Your Data" box (fixed).
- **`costs.py`'s recalc functions (`recalc_landed`, `recalc_profit`, etc.) must stay
  defensive** (`_safe_float` fallback to 0 instead of raising) — they now run on *every*
  `watches/update` PATCH, not just sale-related ones, because the Admin tab's Quick Patch can
  put arbitrary text into any `EDITABLE_FIELDS` value. An unguarded `float()` on a bad value
  (e.g. a string in `sale_price_usd`) would 502 on that watch's every future edit, including
  the corrective one — a self-locking bug, caught during testing before it hit real data. If
  you add a new recalc path, coerce through `_safe_float`, don't add a bare `float()`.
- Streamlit's fancy `st.selectbox`/`st.multiselect` (BaseWeb components, not native
  `<select>`) don't reliably respond to browser-automation `form_input` calls the way a plain
  `<select>` would — a selectbox set this way can silently keep its prior value while a
  submit button click still fires. Prefer opening the dropdown and clicking the option, or
  verify via a follow-up read rather than trusting the "filled" confirmation alone.

## Deferred / open TODOs

- Live eBay API push (currently CSV bulk-upload draft, still a manual Seller Hub step)
- Automated FX rate lookup for the bid calculator (currently manual entry)
- Bulk photo upload (currently one presigned URL at a time)
- `export.py` (DynamoDB → CSV) exists but untested end-to-end
- No delete/edit endpoint for lifecycle transitions — correcting a duplicate stage-transition
  currently means patching `total_labor_hours` directly, which is a hack
