"""
Import Shipment — upload a Buyee invoice PDF, let Claude parse it,
review & edit each line, then bulk-import into the system.
"""
import base64
import json
import streamlit as st
import api
from constants import VALID_STATUSES, STATUS_LABELS, BRANDS
from logger import log

# ---------------------------------------------------------------------------
# Anthropic client (lazy init so the page loads even without the key set)
# ---------------------------------------------------------------------------
def _anthropic_client():
    try:
        import anthropic
        return anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
    except KeyError:
        st.error("ANTHROPIC_API_KEY not found in secrets.toml. Add it and restart.")
        st.stop()


# ---------------------------------------------------------------------------
# Claude collection guesser
# ---------------------------------------------------------------------------
def _guess_collection(reference: str) -> str:
    if not reference:
        return ""
    ref = reference.upper()
    prefix_map = {
        "7B": "Brightz",
        "7T": "Spirit",
        "7N": "Spirit",
        "7S": "5",
        "7A": "Spirit",
        "SBGW": "Grand Seiko",
        "SBGA": "Grand Seiko",
        "SARB": "Presage",
        "SARX": "Presage",
        "SSRP": "Presage",
        "SBDC": "Prospex",
        "SNE":  "Prospex",
        "SRP":  "Turtle",
        "SLA":  "Prospex",
        "SSC":  "Prospex",
        "SCVS": "Brightz",
        "SDGM": "Prospex",
        "NQ":   "Citizen Exceed",
        "AT":   "Citizen Attesa",
        "BZ":   "Citizen Eco-Drive",
        "CB":   "Citizen Satellite Wave",
    }
    for prefix, collection in prefix_map.items():
        if ref.startswith(prefix):
            return collection
    return ""


def _guess_brand(reference: str) -> str:
    if not reference:
        return ""
    ref = reference.upper()
    seiko_prefixes = ("7B", "7T", "7N", "7S", "7A", "SBGW", "SBGA", "SARB", "SARX",
                      "SSRP", "SBDC", "SNE", "SRP", "SLA", "SSC", "SCVS", "SDGM")
    citizen_prefixes = ("NQ", "AT", "BZ", "CB", "AR")
    casio_prefixes = ("GW", "GA", "GBA", "DW", "EFR", "EFS")
    for p in seiko_prefixes:
        if ref.startswith(p):
            return "Seiko"
    for p in citizen_prefixes:
        if ref.startswith(p):
            return "Citizen"
    for p in casio_prefixes:
        if ref.startswith(p):
            return "Casio"
    return ""


# ---------------------------------------------------------------------------
# Claude parse prompt
# ---------------------------------------------------------------------------
PARSE_PROMPT = """
You are parsing a Buyee (Japanese proxy auction service) invoice PDF written in Japanese.
Extract every purchased line-item. Return ONLY valid JSON — no markdown, no explanation.

For each item, determine whether it is a **watch** (complete timepiece) or a **part**
(accessory, bracelet, strap, crown, crystal, movement, tool, etc.).

Return a JSON object with this exact structure:
{
  "invoice_id": "<invoice number from the PDF, or null>",
  "items": [
    {
      "line_num": 1,
      "item_type": "watch",          // "watch" or "part"
      "description_en": "...",       // English translation of the item description
      "description_ja": "...",       // Original Japanese text (copy verbatim)
      "reference": "...",            // Model/caliber reference extracted from text, e.g. "7B22-0AY0"
      "brand": "...",                // Brand if detectable (Seiko / Citizen / Casio / Orient / etc.), else ""
      "collection": "...",           // Collection name if guessable, else ""
      "auction_price_jpy": 0,        // Item hammer price in JPY (integer)
      "buyee_plan_jpy": 0,           // Buyee plan/membership fee for this item in JPY
      "buyee_service_jpy": 0,        // Buyee service fee for this item in JPY
      "domestic_shipping_jpy": 0,    // Domestic (Japan) shipping cost for this item in JPY
      "notes": ""                    // Any extra notes (coupon applied, condition mentions, etc.)
    }
  ],
  "intl_shipping_jpy": 0,            // International shipping total (page 2 summary)
  "customs_duty_jpy": 0,             // Customs/import duty total
  "other_fees_jpy": 0,               // Any other fees not captured above
  "grand_total_jpy": 0               // Grand total as shown on the invoice
}

Rules:
- Extract JPY amounts as integers (strip ¥ and commas).
- If a coupon/discount was applied to an item, note it in "notes" and use the post-discount price.
- If page 2 shows a consolidated fee breakdown, match fees back to each item using item order.
- If a value is missing or unclear, use 0 (numbers) or "" (strings) — never null for numbers.
- Do NOT invent data. If you cannot read something, leave it blank.
"""


def _run_import(items: list, meta: dict):
    fx = meta["fx_rate"]
    invoice_id = meta.get("invoice_id", "")
    results = []

    progress = st.progress(0, text="Starting import…")
    to_process = [i for i in items if i["action"] in ("import", "merge", "part")]
    total = len(to_process)

    for step, item in enumerate(to_process):
        label = item["description_en"] or item["reference"] or f"Item {step+1}"
        progress.progress(step / total, text=f"Processing: {label}")

        try:
            if item["action"] == "import":
                # ── Build USD costs from JPY ──────────────────────────
                auction_jpy = item["auction_price_jpy"]
                intl_usd    = round(item["intl_shipping_jpy"] / fx, 2) if fx else 0
                customs_usd = round(item["customs_duty_jpy"] / fx, 2) if fx else 0
                auction_usd = round(auction_jpy / fx, 2) if fx else 0

                payload = {
                    "brand":                  item["brand"],
                    "collection":             item["collection"],
                    "reference":              item["reference"] or "UNKNOWN",
                    "is_personal":            item["is_personal"],
                    "auction_price_jpy":      auction_jpy,
                    "auction_price_usd":      auction_usd,
                    "buyee_platform_jpy":     item["buyee_platform_jpy"],
                    "buyee_inspection_jpy":   item["buyee_inspection_jpy"],
                    "domestic_shipping_jpy":  item["domestic_shipping_jpy"],
                    "intl_shipping_usd":      intl_usd,
                    "customs_duty_usd":       customs_usd,
                    "notes":                  (
                        f"Imported from invoice {invoice_id}. {item['notes']}".strip(". ")
                        if invoice_id else item["notes"]
                    ),
                }
                watch_resp = api.create_watch(payload)
                watch_id   = watch_resp["watch_id"]

                # Log initial transition if status differs from default create status
                if item["initial_status"] and item["initial_status"] != "won":
                    try:
                        api.add_transition(
                            watch_id,
                            to_status=item["initial_status"],
                            hours_spent=0,
                            notes=(
                                f"Initial status set on import from {invoice_id}"
                                if invoice_id else "Initial status set on import"
                            ),
                        )
                    except Exception:
                        pass  # Non-fatal: watch was created successfully

                results.append({"ok": True, "label": label, "watch_id": watch_id, "action": "created"})

            elif item["action"] == "merge":
                # ── Patch cost fields into an existing watch ──────────
                watch_id = item.get("merge_into")
                if not watch_id:
                    results.append({"ok": False, "label": label, "error": "No target watch selected for merge"})
                    continue

                auction_jpy = item["auction_price_jpy"]
                intl_usd    = round(item["intl_shipping_jpy"] / fx, 2) if fx else 0
                customs_usd = round(item["customs_duty_jpy"] / fx, 2) if fx else 0
                auction_usd = round(auction_jpy / fx, 2) if fx else 0

                patch = {
                    "auction_price_jpy":      auction_jpy,
                    "auction_price_usd":      auction_usd,
                    "buyee_platform_jpy":     item["buyee_platform_jpy"],
                    "buyee_inspection_jpy":   item["buyee_inspection_jpy"],
                    "domestic_shipping_jpy":  item["domestic_shipping_jpy"],
                    "intl_shipping_usd":      intl_usd,
                    "customs_duty_usd":       customs_usd,
                }
                # Append invoice reference to notes without overwriting existing notes
                if invoice_id:
                    patch["notes"] = f"Cost fields updated from invoice {invoice_id}"

                api.update_watch(watch_id, patch)
                results.append({"ok": True, "label": label, "watch_id": watch_id, "action": "merged"})

            elif item["action"] == "part":
                if not item.get("part_assign_to"):
                    results.append({"ok": False, "label": label, "error": "No watch assigned"})
                    continue
                total_jpy = (
                    item["auction_price_jpy"]
                    + item["buyee_platform_jpy"]
                    + item["buyee_inspection_jpy"]
                    + item["domestic_shipping_jpy"]
                )
                amount_usd = round(total_jpy / fx, 2) if fx else 0
                api.add_cost(
                    item["part_assign_to"],
                    amount_usd=amount_usd,
                    category="part",
                    notes=f"{label} (from invoice {invoice_id})" if invoice_id else label,
                )
                results.append({"ok": True, "label": label, "watch_id": item["part_assign_to"], "action": "cost_added"})

        except Exception as e:
            log.error("import item failed: %s — %s", label, e, exc_info=True)
            results.append({"ok": False, "label": label, "error": str(e)})

    progress.progress(1.0, text="Done!")
    ok_count  = sum(1 for r in results if r["ok"])
    err_count = sum(1 for r in results if not r["ok"])
    log.info("import complete  ok=%d  errors=%d  invoice=%s", ok_count, err_count, invoice_id)
    st.session_state["import_results"] = results
    st.session_state["import_done"] = True
    st.rerun()


@st.cache_data(show_spinner=False)
def _parse_invoice(pdf_bytes: bytes) -> dict:
    client = _anthropic_client()
    import anthropic
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")
    msg = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": pdf_b64,
                    },
                },
                {"type": "text", "text": PARSE_PROMPT},
            ],
        }],
    )
    raw = msg.content[0].text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    parsed = json.loads(raw.strip())
    log.info("_parse_invoice OK  invoice=%s  items=%d",
             parsed.get("invoice_id"), len(parsed.get("items", [])))
    return parsed


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Import Shipment", layout="wide", page_icon="📦")
st.title("📦 Import Shipment from PDF Invoice")

# ── Session state keys ──────────────────────────────────────────────────────
if "import_parsed" not in st.session_state:
    st.session_state["import_parsed"] = None     # raw dict from Claude
if "import_items" not in st.session_state:
    st.session_state["import_items"] = []        # list of per-item dicts (editable)
if "import_meta" not in st.session_state:
    st.session_state["import_meta"] = {}         # invoice_id, intl, customs, etc.
if "import_done" not in st.session_state:
    st.session_state["import_done"] = False

# ── Step indicator ──────────────────────────────────────────────────────────
phase = "upload"
if st.session_state["import_parsed"] is not None:
    phase = "review"
if st.session_state["import_done"]:
    phase = "done"

st.markdown(
    f"**Step 1 — Upload** {'✅' if phase in ('review','done') else '👈'}  ·  "
    f"**Step 2 — Review** {'✅' if phase == 'done' else ('👈' if phase == 'review' else '⬜')}  ·  "
    f"**Step 3 — Import** {'✅' if phase == 'done' else '⬜'}"
)
st.divider()

# ===========================================================================
# STEP 1 — UPLOAD
# ===========================================================================
if phase == "upload":
    uploaded = st.file_uploader("Upload Buyee invoice PDF", type=["pdf"])
    fx = st.number_input("USD/JPY exchange rate (e.g. 155.0)", min_value=50.0, max_value=300.0, value=150.0, step=0.5)

    if uploaded and st.button("Parse with Claude ✨", type="primary"):
        with st.spinner("Sending to Claude… this takes ~10 seconds"):
            try:
                result = _parse_invoice(uploaded.read())
            except Exception as e:
                st.error(f"Claude parse failed: {e}")
                st.stop()

        # Store invoice-level fields
        meta = {
            "invoice_id":     result.get("invoice_id", ""),
            "intl_shipping_jpy": int(result.get("intl_shipping_jpy", 0)),
            "customs_duty_jpy":  int(result.get("customs_duty_jpy", 0)),
            "other_fees_jpy":    int(result.get("other_fees_jpy", 0)),
            "grand_total_jpy":   int(result.get("grand_total_jpy", 0)),
            "fx_rate":           fx,
        }
        st.session_state["import_meta"] = meta

        # Enrich each item with guessed values and editable defaults
        items = []
        raw_items = result.get("items", [])
        n_watches = sum(1 for i in raw_items if i.get("item_type") == "watch")
        intl_per_watch = round(meta["intl_shipping_jpy"] / n_watches, 0) if n_watches else 0
        customs_per_watch = round(meta["customs_duty_jpy"] / n_watches, 0) if n_watches else 0

        for raw in raw_items:
            ref = raw.get("reference", "")
            brand = raw.get("brand") or _guess_brand(ref)
            collection = raw.get("collection") or _guess_collection(ref)
            is_watch = raw.get("item_type") == "watch"
            item = {
                # Classification
                "item_type":          raw.get("item_type", "watch"),
                "action":             "import" if is_watch else ("part" if not is_watch else "skip"),
                # Identity
                "description_en":     raw.get("description_en", ""),
                "description_ja":     raw.get("description_ja", ""),
                "reference":          ref,
                "brand":              brand,
                "collection":         collection,
                "notes":              raw.get("notes", ""),
                # Costs JPY
                "auction_price_jpy":       int(raw.get("auction_price_jpy", 0)),
                "buyee_platform_jpy":      int(raw.get("buyee_plan_jpy", 0)),
                "buyee_inspection_jpy":    int(raw.get("buyee_service_jpy", 0)),
                "domestic_shipping_jpy":   int(raw.get("domestic_shipping_jpy", 0)),
                "intl_shipping_jpy":       int(intl_per_watch) if is_watch else 0,
                "customs_duty_jpy":        int(customs_per_watch) if is_watch else 0,
                # Watch-specific
                "initial_status":     "received",
                "is_personal":        False,
                # Part-specific / merge
                "part_assign_to":     "",   # watch_id to attach as additional cost
                "merge_into":         "",   # watch_id to merge costs into
            }
            items.append(item)

        st.session_state["import_items"] = items
        st.session_state["import_parsed"] = result
        st.rerun()

# ===========================================================================
# STEP 2 — REVIEW
# ===========================================================================
elif phase == "review":
    meta = st.session_state["import_meta"]
    items = st.session_state["import_items"]

    st.subheader("Invoice summary")
    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric("Invoice", meta.get("invoice_id") or "—")
    mc2.metric("Intl Shipping", f"¥{meta['intl_shipping_jpy']:,}")
    mc3.metric("Customs", f"¥{meta['customs_duty_jpy']:,}")
    mc4.metric("Grand Total", f"¥{meta['grand_total_jpy']:,}")

    fx = meta["fx_rate"]
    fcol1, fcol2 = st.columns([2, 1])
    with fcol1:
        st.caption(f"Exchange rate used: **¥{fx} / $1**")
    with fcol2:
        new_fx = st.number_input("Adjust FX rate", value=fx, step=0.5, key="review_fx", label_visibility="collapsed")
        if new_fx != fx:
            st.session_state["import_meta"]["fx_rate"] = new_fx
            fx = new_fx

    st.divider()
    st.subheader("Line items")

    # Fetch existing watches for part-assignment dropdown
    try:
        existing_watches = api.list_watches()
        watch_labels = {
            f"[{w['watch_id']}] {w['brand']} {w['collection']} {w['reference']}": w["watch_id"]
            for w in existing_watches
        }
    except Exception:
        existing_watches = []
        watch_labels = {}

    for idx, item in enumerate(items):
        icon = "⌚" if item["item_type"] == "watch" else "🔩"
        label = f"{icon} **{idx+1}. {item['description_en'] or item['description_ja'] or 'Item'}**"
        if item["reference"]:
            label += f"  `{item['reference']}`"
        with st.expander(label, expanded=True):
            col_a, col_b = st.columns([2, 1])

            with col_a:
                # Action selector
                if item["item_type"] == "watch":
                    action_options = ["import as new watch", "merge into existing watch", "skip"]
                else:
                    action_options = ["add as cost to watch", "skip"]

                # Map stored action → display label
                _stored_to_label = {
                    "import": "import as new watch",
                    "merge":  "merge into existing watch",
                    "part":   "add as cost to watch",
                    "skip":   "skip",
                }
                _label_to_stored = {v: k for k, v in _stored_to_label.items()}

                current_label = _stored_to_label.get(item["action"], action_options[0])
                if current_label not in action_options:
                    current_label = action_options[0]

                chosen_action = st.radio(
                    "Action",
                    action_options,
                    index=action_options.index(current_label),
                    key=f"action_{idx}",
                    horizontal=True,
                )
                item["action"] = _label_to_stored.get(chosen_action, "skip")

                if item["action"] == "import":
                    c1, c2, c3 = st.columns(3)
                    item["brand"] = c1.selectbox(
                        "Brand", BRANDS,
                        index=BRANDS.index(item["brand"]) if item["brand"] in BRANDS else 0,
                        key=f"brand_{idx}",
                    )
                    item["collection"] = c2.text_input("Collection", value=item["collection"], key=f"coll_{idx}")
                    item["reference"] = c3.text_input("Reference", value=item["reference"], key=f"ref_{idx}")

                    sc1, sc2 = st.columns(2)
                    status_opts = [s for s in VALID_STATUSES if s not in ("sold", "shipped")]
                    item["initial_status"] = sc1.selectbox(
                        "Initial status",
                        status_opts,
                        index=status_opts.index(item["initial_status"]) if item["initial_status"] in status_opts else status_opts.index("received"),
                        format_func=lambda s: STATUS_LABELS.get(s, s),
                        key=f"status_{idx}",
                    )
                    item["is_personal"] = sc2.checkbox("Personal", value=item["is_personal"], key=f"personal_{idx}")

                elif item["action"] == "merge":
                    if watch_labels:
                        chosen_label = st.selectbox(
                            "Merge costs into watch",
                            ["— select —"] + list(watch_labels.keys()),
                            key=f"mergewatch_{idx}",
                            help="Updates the existing watch record with the JPY/USD cost fields from this invoice. No new watch is created.",
                        )
                        item["merge_into"] = watch_labels.get(chosen_label, "")
                    else:
                        st.warning("No existing watches found.")

                elif item["action"] == "part":
                    if watch_labels:
                        chosen_label = st.selectbox(
                            "Assign cost to watch",
                            ["— select —"] + list(watch_labels.keys()),
                            key=f"partwatch_{idx}",
                        )
                        item["part_assign_to"] = watch_labels.get(chosen_label, "")
                    else:
                        st.warning("No watches found to assign this cost to.")

                if item["notes"]:
                    st.caption(f"📎 {item['notes']}")
                if item["description_ja"]:
                    st.caption(f"🇯🇵 {item['description_ja']}")

            with col_b:
                st.markdown("**Costs (JPY)**")
                item["auction_price_jpy"]     = st.number_input("Auction price", value=item["auction_price_jpy"], step=100, key=f"auction_{idx}")
                item["buyee_platform_jpy"]     = st.number_input("Plan fee", value=item["buyee_platform_jpy"], step=100, key=f"plan_{idx}")
                item["buyee_inspection_jpy"]   = st.number_input("Service fee", value=item["buyee_inspection_jpy"], step=100, key=f"svc_{idx}")
                item["domestic_shipping_jpy"]  = st.number_input("Dom. shipping", value=item["domestic_shipping_jpy"], step=100, key=f"domship_{idx}")
                if item["item_type"] == "watch":
                    item["intl_shipping_jpy"]  = st.number_input("Intl shipping (alloc.)", value=item["intl_shipping_jpy"], step=100, key=f"intlship_{idx}")
                    item["customs_duty_jpy"]   = st.number_input("Customs (alloc.)", value=item["customs_duty_jpy"], step=100, key=f"customs_{idx}")

                # Live USD preview
                total_jpy = (
                    item["auction_price_jpy"]
                    + item["buyee_platform_jpy"]
                    + item["buyee_inspection_jpy"]
                    + item["domestic_shipping_jpy"]
                    + item.get("intl_shipping_jpy", 0)
                    + item.get("customs_duty_jpy", 0)
                )
                total_usd = round(total_jpy / fx, 2) if fx else 0
                st.metric("Est. landed (USD)", f"${total_usd:,.2f}", help=f"¥{total_jpy:,} ÷ {fx}")

    # Save updated items back (widgets wrote into item dicts directly via mutable refs)
    st.session_state["import_items"] = items

    st.divider()

    # Summary of what will happen
    to_import = [i for i in items if i["action"] == "import"]
    to_merge  = [i for i in items if i["action"] == "merge"]
    to_part   = [i for i in items if i["action"] == "part"]
    to_skip   = [i for i in items if i["action"] == "skip"]
    st.markdown(
        f"**Ready:** {len(to_import)} new watch(es)  ·  "
        f"{len(to_merge)} merge(s)  ·  "
        f"{len(to_part)} part cost(s)  ·  "
        f"{len(to_skip)} skipped"
    )

    col_back, col_go = st.columns([1, 3])
    with col_back:
        if st.button("← Start over"):
            st.session_state["import_parsed"] = None
            st.session_state["import_items"] = []
            st.session_state["import_meta"] = {}
            st.rerun()
    with col_go:
        nothing_to_do = (len(to_import) == 0 and len(to_merge) == 0 and len(to_part) == 0)
        if st.button("Import now 🚀", type="primary", disabled=nothing_to_do):
            log.info("import started  new=%d merge=%d parts=%d  invoice=%s",
                     len(to_import), len(to_merge), len(to_part),
                     meta.get("invoice_id"))
            _run_import(items, meta)

# ===========================================================================
# STEP 3 — DONE
# ===========================================================================
elif phase == "done":
    st.success("Import complete! ✅")
    results = st.session_state.get("import_results", [])
    _action_tag = {"created": "new watch", "merged": "merged", "cost_added": "cost added"}
    for r in results:
        if r["ok"]:
            tag = _action_tag.get(r.get("action", ""), r.get("action", ""))
            st.markdown(f"✅ {r['label']} → `{r.get('watch_id','')}` _{tag}_")
        else:
            st.markdown(f"❌ {r['label']} — {r['error']}")

    if st.button("Import another invoice"):
        for key in ["import_parsed", "import_items", "import_meta", "import_done", "import_results"]:
            st.session_state.pop(key, None)
        st.rerun()
