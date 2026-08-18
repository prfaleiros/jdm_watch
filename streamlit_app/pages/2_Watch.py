import streamlit as st
import pandas as pd
from decimal import Decimal, ROUND_HALF_UP
from datetime import date as date_type
import api
from constants import (
    VALID_STATUSES, STATUS_LABELS, ACTIVE_STATUSES,
    PHOTO_SLOTS, CASE_MATERIALS, CRYSTAL_TYPES, BRACELET_MATERIALS,
    COST_CATEGORIES, SALE_PLATFORMS, BRANDS, CALIBER_HINTS,
    SHIPPING_LABEL_SOURCES, SHIPPING_LABEL_SOURCE_LABELS,
)
from logger import log


# ── Pricing helper (client-side what-if, no API call) ──────────────────────────

def _calc_ebay_price(landed, labor_hrs, labor_rate, shipping,
                     ebay_fvf, tax_blend, ad_rate_pct, roi_pct, min_profit):
    L   = Decimal(str(landed))
    lc  = Decimal(str(labor_hrs)) * Decimal(str(labor_rate))
    sh  = Decimal(str(shipping))
    eff = Decimal(str(ebay_fvf)) * (Decimal("1") + Decimal(str(tax_blend))) \
          + Decimal(str(ad_rate_pct)) / Decimal("100")
    roi = Decimal(str(roi_pct)) / Decimal("100")
    floor = Decimal(str(min_profit))
    target = max(L * roi, floor)
    price  = (L + lc + sh + target) / (Decimal("1") - eff)
    return (
        float(price.quantize(Decimal("0.01"), ROUND_HALF_UP)),
        float(target.quantize(Decimal("0.01"), ROUND_HALF_UP)),
    )


def _calc_direct_price(landed, labor_hrs, labor_rate, shipping,
                       pp_rate, pp_flat, roi_pct, min_profit):
    L     = Decimal(str(landed))
    lc    = Decimal(str(labor_hrs)) * Decimal(str(labor_rate))
    sh    = Decimal(str(shipping))
    roi   = Decimal(str(roi_pct)) / Decimal("100")
    floor = Decimal(str(min_profit))
    target = max(L * roi, floor)
    price  = (L + lc + sh + target + Decimal(str(pp_flat))) \
             / (Decimal("1") - Decimal(str(pp_rate)))
    return float(price.quantize(Decimal("0.01"), ROUND_HALF_UP))


# ── Pitch generation (Streamlit-side Claude call) ──────────────────────────────

def _generate_pitch(watch: dict) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])

    ref        = watch.get("reference", "")
    brand      = watch.get("brand", "")
    collection = watch.get("collection", "")
    material   = watch.get("case_material", "")
    solar      = watch.get("solar", False)
    radio      = watch.get("radio_sync", False)
    color      = watch.get("color", "")
    diameter   = watch.get("diameter_mm", "")
    notes      = watch.get("notes", "")

    # Look up the best matching caliber hint
    hint = ""
    for prefix, text in CALIBER_HINTS.items():
        if ref.upper().startswith(prefix.upper()):
            hint = f"\nCaliber note: {text}"
            break

    features = []
    if solar:    features.append("Solar powered (light-harvesting, no battery)")
    if radio:    features.append("Radio-controlled (self-setting, atomic accuracy)")
    if material == "Titanium": features.append("Titanium case (lightweight, hypoallergenic)")
    elif material:             features.append(f"{material} case")

    prompt = (
        f"Write a 3–4 sentence 'why buy this watch' pitch for a JDM watch listing.\n\n"
        f"Watch: {brand} {collection} {ref}\n"
        + (f"Dial: {color}\n" if color else "")
        + (f"Size: {diameter}mm\n" if diameter else "")
        + (f"Notable features: {', '.join(features)}\n" if features else "")
        + hint + "\n"
        + (f"Seller notes: {notes}\n" if notes else "")
        + "\n"
        "Tone: educational and genuinely enthusiastic — help the buyer understand "
        "why this piece is interesting, not just what it is. Lead with the most "
        "unique or impressive aspect.\n"
        "Rules:\n"
        "• Do NOT mention features the watch doesn't have.\n"
        "• Do NOT make geographic coverage claims for radio signals.\n"
        "• No bullet points — flowing prose only.\n"
        "• 3–4 sentences max."
    )

    msg = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip()


# ── Photo-first spec identification (Streamlit-side Claude call) ───────────────

LOOKUP_PROMPT_PHOTO = """You are a watch identification expert specializing in Japanese domestic market (JDM) watches.

You are given one or more photos of a watch, plus any existing attributes already recorded for it (treat these as context hints, not ground truth).

Your task: study the photos to identify the exact model, read visible text from the caseback or dial, and return all specifications you can determine.

Return ONLY valid JSON — no markdown, no explanation — with this exact structure:
{
  "notes": "any caveats, identification uncertainty, or notable observations",
  "identified_reference": "7B24-0BH0",
  "identified_brand": "Seiko",
  "discrepancies": [],
  "specs": {
    "reference":         {"value": "7B24-0BH0",           "confidence": "certain",  "source": "caseback"},
    "collection":        {"value": "Brightz",              "confidence": "certain",  "source": "caliber_knowledge"},
    "jdm_model":         {"value": "SACM171",              "confidence": "likely",   "source": "caliber_knowledge"},
    "movement_type":     {"value": "Solar Radio Quartz",   "confidence": "certain",  "source": "caliber_knowledge"},
    "solar":             {"value": true,                   "confidence": "certain",  "source": "dial"},
    "radio_sync":        {"value": true,                   "confidence": "certain",  "source": "caliber_knowledge"},
    "diameter_mm":       {"value": 38.5,                   "confidence": "likely",   "source": "caliber_knowledge"},
    "thickness_mm":      {"value": 10.5,                   "confidence": "likely",   "source": "caliber_knowledge"},
    "lug_width_mm":      {"value": 20.0,                   "confidence": "likely",   "source": "caliber_knowledge"},
    "case_material":     {"value": "Stainless Steel",      "confidence": "certain",  "source": "caseback"},
    "crystal_type":      {"value": "Hardlex",              "confidence": "certain",  "source": "caliber_knowledge"},
    "color":             {"value": "Blue",                 "confidence": "certain",  "source": "dial"},
    "bracelet_material": {"value": "Stainless Steel",      "confidence": "certain",  "source": "caseback"},
    "water_resistance":  {"value": "100m",                 "confidence": "certain",  "source": "caseback"},
    "jewel_count":       {"value": 0,                      "confidence": "certain",  "source": "caliber_knowledge"},
    "power_reserve":     {"value": "Indefinite (Solar)",   "confidence": "certain",  "source": "caliber_knowledge"}
  }
}

Source values:
- "caseback": text/markings read directly from the caseback photo
- "dial": read from the dial photo
- "box_papers": read from box or papers photo
- "caliber_knowledge": derived from your training data for this caliber/reference
- "context_attribute": taken from the existing watch record provided as context

Confidence levels:
- "certain": read directly from a photo, or definitively documented for this specific reference
- "likely": well-documented but may vary by production run or regional variant
- "uncertain": educated guess — always flag

Critical rules:
- NEVER include lug_to_lug_mm — always measured manually, never guessed
- If the reference is not readable from any photo, set "identified_reference" to null and
  mark the reference spec as "uncertain"
- If photos contradict the existing record, add a plain-English entry to "discrepancies"
- Never fabricate specs for a reference you don't actually recognise — mark unknown fields
  as "uncertain" with source "caliber_knowledge"
- jewel_count: 0 for quartz; omit entirely if you cannot determine it
- solar / radio_sync: always boolean true/false, never strings
- diameter_mm, thickness_mm, lug_width_mm: numbers, not strings
- power_reserve: plain text ("40h", "Indefinite (Solar)", "6 months (Kinetic)", etc.)
"""


def _identify_from_photos(watch: dict, photos: list) -> dict:
    """Photo-first watch identification.

    photos: list of (bytes, mime_type) tuples — first photo should ideally be caseback.
    watch:  existing watch record used as context/cross-check, not as truth.
    """
    import anthropic, base64, json as _json
    client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])

    # Build content: all photo blocks first, then context text + prompt
    content = []
    for photo_bytes, photo_mime in photos:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": photo_mime,
                "data": base64.standard_b64encode(photo_bytes).decode(),
            },
        })

    # Build context from existing watch attributes (non-empty only)
    ctx_fields = [
        "brand", "collection", "reference", "jdm_model", "case_material",
        "color", "solar", "radio_sync", "diameter_mm", "crystal_type",
        "bracelet_material", "water_resistance", "movement_type",
    ]
    ctx_lines = ["Existing watch record (context / cross-check only — photos are primary truth):"]
    for f in ctx_fields:
        val = watch.get(f)
        if val is not None and val != "" and val is not False:
            ctx_lines.append(f"  {f}: {val}")

    content.append({
        "type": "text",
        "text": "\n".join(ctx_lines) + "\n\n" + LOOKUP_PROMPT_PHOTO,
    })

    msg = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1500,
        messages=[{"role": "user", "content": content}],
    )
    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    result = _json.loads(raw.strip())
    log.info(
        "photo lookup OK  watch=%s  identified_ref=%s  fields=%d",
        watch.get("watch_id", "?"),
        result.get("identified_reference"),
        len(result.get("specs", {})),
    )
    return result

st.set_page_config(page_title="Watch Detail", layout="wide", page_icon="⌚")


# ── Watch selector ────────────────────────────────────────────────────────────

@st.cache_data(ttl=30)
def load_list():
    return api.list_watches()

try:
    all_watches = load_list()
except Exception as e:
    st.error(f"Could not load watch list: {e}")
    st.stop()

if not all_watches:
    st.warning("No watches in inventory.")
    st.stop()

label_to_id = {
    f"[{w['watch_id']}] {w['brand']} {w['collection']} {w['reference']} · {STATUS_LABELS.get(w['current_status'], w['current_status'])}": w["watch_id"]
    for w in all_watches
}

default_id = st.session_state.get("selected_watch_id")
labels = list(label_to_id.keys())
default_idx = next((i for i, k in enumerate(labels) if label_to_id[k] == default_id), 0)

chosen_label = st.selectbox("Watch", labels, index=default_idx)
watch_id = label_to_id[chosen_label]
st.session_state["selected_watch_id"] = watch_id


# ── Load full watch record ────────────────────────────────────────────────────

try:
    watch = api.get_watch(watch_id)
except Exception as e:
    st.error(f"Could not load watch: {e}")
    st.stop()

transitions = watch.get("transitions", [])
costs = watch.get("additional_costs", [])

# Header
personal_badge = " 🔒 Personal" if watch.get("is_personal") else ""
status_label = STATUS_LABELS.get(watch["current_status"], watch["current_status"])
st.markdown(
    f"## {watch.get('brand','')} {watch.get('collection','')} {watch.get('jdm_model','')}"
    f"&nbsp;&nbsp;<span style='font-size:0.85em;color:gray'>{watch.get('reference','')}{personal_badge}</span>",
    unsafe_allow_html=True,
)
header_cost_basis = watch.get("total_cost_basis_usd") or watch.get("total_landed_cost_usd") or 0
st.caption(f"Status: **{status_label}**  ·  ID: `{watch_id}`  ·  Cost: **${header_cost_basis:,.2f}**")

st.divider()


# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_overview, tab_edit, tab_transitions, tab_costs, tab_photos, tab_listing, tab_admin = st.tabs(
    ["Overview", "Edit", "Transitions", "Costs", "Photos", "Listing", "Admin"]
)


# ── Overview ──────────────────────────────────────────────────────────────────

with tab_overview:
    col_specs, col_costs = st.columns(2)

    with col_specs:
        st.subheader("Specifications")
        specs = {
            "Brand":          watch.get("brand"),
            "Collection":     watch.get("collection"),
            "Reference":      watch.get("reference"),
            "JDM Model":      watch.get("jdm_model"),
            "Serial":         watch.get("serial"),
            "Case Material":  watch.get("case_material"),
            "Diameter":       f"{watch['diameter_mm']} mm" if watch.get("diameter_mm") else None,
            "Lug to Lug":     f"{watch['lug_to_lug_mm']} mm" if watch.get("lug_to_lug_mm") else None,
            "Thickness":      f"{watch['thickness_mm']} mm" if watch.get("thickness_mm") else None,
            "Lug Width":      f"{watch['lug_width_mm']} mm" if watch.get("lug_width_mm") else None,
            "Dial Color":     watch.get("color"),
            "Movement":       watch.get("movement_type"),
            "Crystal":        watch.get("crystal_type"),
            "Bracelet":       watch.get("bracelet_material"),
            "Water Resist.":  watch.get("water_resistance"),
            "Power Reserve":  watch.get("power_reserve"),
            "Jewels":         f"{watch['jewel_count']}J" if watch.get("jewel_count") else None,
            "Solar":          "Yes" if watch.get("solar") else None,
            "Radio Sync":     "Yes" if watch.get("radio_sync") else None,
        }
        for label, value in specs.items():
            if value:
                st.markdown(f"**{label}:** {value}")

    with col_costs:
        st.subheader("Cost Breakdown")
        auction_usd = watch.get("auction_price_usd") or 0
        auction_jpy = watch.get("auction_price_jpy") or 0
        customs = watch.get("customs_duty_usd") or 0
        intl_ship = watch.get("intl_shipping_usd") or 0
        presale = watch.get("total_presale_costs_usd") or 0
        additional = watch.get("total_additional_costs_usd") or 0
        labor_hrs = watch.get("total_labor_hours") or 0

        jpy_rate = auction_usd / auction_jpy if auction_jpy else 0
        buyee_jpy = (
            (watch.get("buyee_platform_jpy") or 0)
            + (watch.get("buyee_inspection_jpy") or 0)
            + (watch.get("domestic_shipping_jpy") or 0)
        )
        buyee_usd = buyee_jpy * jpy_rate if jpy_rate else 0

        rows = [
            ("Auction (JPY)", f"¥{auction_jpy:,.0f}" if auction_jpy else "—"),
            ("Auction (USD)", f"${auction_usd:,.2f}" if auction_usd else "—"),
            ("Buyee Fees", f"~${buyee_usd:,.2f}" if buyee_usd else "—"),
            ("Customs Duty", f"${customs:,.2f}" if customs else "—"),
            ("Intl Shipping (alloc.)", f"${intl_ship:,.2f}" if intl_ship else "—"),
            ("Pre-sale Costs (parts/repair)", f"${presale:,.2f}" if presale else "—"),
            ("Additional Costs (all, incl. pre-sale)", f"${additional:,.2f}" if additional else "—"),
            ("Labor", f"{labor_hrs:.2g} hrs"),
        ]
        cost_df = pd.DataFrame(rows, columns=["Item", "Amount"])
        st.dataframe(cost_df, hide_index=True, width='stretch')

        cost_basis = watch.get("total_cost_basis_usd") or watch.get("total_landed_cost_usd") or 0
        cbm1, cbm2 = st.columns(2)
        cbm1.metric("Landed (acquisition only)", f"${watch.get('total_landed_cost_usd') or 0:,.2f}")
        cbm2.metric("Cost Basis (landed + pre-sale)", f"${cost_basis:,.2f}")

        if watch.get("sale_price_usd"):
            st.divider()
            net = watch.get("net_profit_usd")
            sc1, sc2 = st.columns(2)
            sc1.metric("Sale Price", f"${watch['sale_price_usd']:,.2f}")
            if net is not None:
                sc2.metric("Net Profit", f"${net:,.2f}", delta=f"${net - cost_basis:,.2f} vs cost basis")

    if watch.get("notes"):
        st.divider()
        st.subheader("Notes")
        st.markdown(watch["notes"])


# ── Edit ──────────────────────────────────────────────────────────────────────

with tab_edit:
    # ── Photo-first spec identification ───────────────────────────────────────
    with st.expander("🔍 Identify from photos", expanded=False):
        st.caption(
            "Upload caseback and/or dial photos — Claude reads the reference, identifies the model, "
            "and proposes specs from the photos. Existing attributes are used as context and cross-checked. "
            "**lug-to-lug is always excluded** — measure it yourself. "
            "Photos are saved to S3 and selectable as the inventory thumbnail."
        )
        lu_photos = st.file_uploader(
            "Photos — caseback first, then dial (JPEG recommended)",
            type=["jpg", "jpeg", "png"],
            accept_multiple_files=True,
            key="lookup_photos",
        )

        if lu_photos and st.button("Identify from photos ✨", key="lookup_btn"):
            if "ANTHROPIC_API_KEY" not in st.secrets:
                st.error("ANTHROPIC_API_KEY not set in secrets.toml.")
            else:
                # Step 1: upload photos to S3 so they persist on the watch record
                uploaded_keys = []
                with st.spinner(f"Uploading {len(lu_photos)} photo(s) to S3…"):
                    for i, f in enumerate(lu_photos):
                        ext      = f.name.rsplit(".", 1)[-1].lower() if "." in f.name else "jpg"
                        filename = f"lookup_{i + 1:02d}.{ext}"
                        try:
                            upload_url = api.get_upload_url(watch_id, filename)
                            api.upload_photo(upload_url, f.getvalue(), f.type or "image/jpeg")
                            s3_key = f"photos/{watch_id}/{filename}"
                            uploaded_keys.append(s3_key)
                            log.info("lookup photo uploaded: %s", s3_key)
                        except Exception as e:
                            st.warning(f"Could not upload {f.name} to S3: {e}")

                # Step 2: pass photos to Claude for identification
                with st.spinner(f"Identifying watch from {len(lu_photos)} photo(s)…"):
                    try:
                        photos_data = [(f.getvalue(), f.type or "image/jpeg") for f in lu_photos]
                        result = _identify_from_photos(watch, photos_data)
                        st.session_state["lookup_result"]   = result
                        st.session_state["lookup_watch_id"] = watch_id
                        st.session_state["lookup_s3_keys"]  = uploaded_keys
                        st.cache_data.clear()   # so Photos tab picks up the new files
                    except Exception as e:
                        st.error(f"Identification failed: {e}")
                        log.error("photo lookup failed for %s: %s", watch_id, e)

        # ── Review UI ────────────────────────────────────────────────────────
        result = st.session_state.get("lookup_result")
        if result and st.session_state.get("lookup_watch_id") == watch_id:

            # Identified identity banner
            id_ref   = result.get("identified_reference")
            id_brand = result.get("identified_brand")
            if id_ref or id_brand:
                st.success(f"📸 Identified: **{id_brand or '?'}** · ref **{id_ref or 'not readable'}**")

            if result.get("notes"):
                st.info(f"ℹ️ {result['notes']}")

            # Discrepancy warnings
            for d in result.get("discrepancies", []):
                st.warning(f"⚠️ {d}")

            specs_found = result.get("specs", {})
            if not specs_found:
                st.warning("No specs returned.")
            else:
                _CONF_ICON   = {"certain": "✅", "likely": "🟡", "uncertain": "⚠️"}
                _SOURCE_ICON = {
                    "caseback":          "🔩",
                    "dial":              "🕐",
                    "box_papers":        "📋",
                    "caliber_knowledge": "📚",
                    "context_attribute": "📝",
                }
                _FIELD_LABELS = {
                    "reference": "Reference", "collection": "Collection",
                    "jdm_model": "JDM Model", "movement_type": "Movement Type",
                    "solar": "Solar", "radio_sync": "Radio Sync",
                    "diameter_mm": "Diameter (mm)", "thickness_mm": "Thickness (mm)",
                    "lug_width_mm": "Lug Width (mm)", "case_material": "Case Material",
                    "crystal_type": "Crystal", "color": "Dial Color",
                    "bracelet_material": "Bracelet Material",
                    "water_resistance": "Water Resistance",
                    "jewel_count": "Jewels", "power_reserve": "Power Reserve",
                }

                st.markdown("**Proposed values** — check the ones you want to apply:")
                selected = {}
                for field, item in specs_found.items():
                    conf        = item.get("confidence", "uncertain")
                    value       = item.get("value")
                    src         = item.get("source", "")
                    conf_icon   = _CONF_ICON.get(conf, "⚠️")
                    src_icon    = _SOURCE_ICON.get(src, "")
                    label       = _FIELD_LABELS.get(field, field)
                    display_val = "Yes" if value is True else ("No" if value is False else str(value))
                    checked     = conf != "uncertain"
                    if st.checkbox(
                        f"{conf_icon}{src_icon} {label}: {display_val}  ({conf})",
                        value=checked, key=f"lu_{field}",
                    ):
                        selected[field] = value

                # Thumbnail selection (only when photos were uploaded this session)
                uploaded_keys = st.session_state.get("lookup_s3_keys", [])
                thumb_sel = None
                if uploaded_keys:
                    st.markdown("---")
                    st.markdown("**Set thumbnail** for inventory view:")
                    thumb_options = ["— keep current —"] + [k.split("/")[-1] for k in uploaded_keys]
                    thumb_sel = st.radio(
                        "Thumbnail", thumb_options, horizontal=True, key="lookup_thumb",
                    )

                if selected and st.button("Apply selected ✓", type="primary", key="apply_lookup"):
                    payload = dict(selected)
                    if thumb_sel and thumb_sel != "— keep current —":
                        idx = [k.split("/")[-1] for k in uploaded_keys].index(thumb_sel)
                        payload["thumbnail_key"] = uploaded_keys[idx]
                    try:
                        api.update_watch(watch_id, payload)
                        st.cache_data.clear()
                        st.session_state.pop("lookup_result", None)
                        st.session_state.pop("lookup_s3_keys", None)
                        st.success(f"Applied {len(selected)} field(s).")
                        log.info("photo lookup applied %d fields to %s", len(payload), watch_id)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Apply failed: {e}")

    st.divider()
    with st.form("edit_watch"):
        st.subheader("Identity")
        ec1, ec2, ec3 = st.columns(3)
        brand      = ec1.selectbox("Brand", BRANDS, index=BRANDS.index(watch.get("brand","")) if watch.get("brand","") in BRANDS else 0)
        collection = ec2.text_input("Collection", value=watch.get("collection",""))
        reference  = ec3.text_input("Reference", value=watch.get("reference",""))

        ec4, ec5 = st.columns(2)
        jdm_model = ec4.text_input("JDM Model", value=watch.get("jdm_model",""))
        serial    = ec5.text_input("Serial", value=watch.get("serial",""))

        st.subheader("Specifications")
        sc1, sc2, sc3, sc4 = st.columns(4)
        diameter    = sc1.number_input("Diameter (mm)",    value=float(watch.get("diameter_mm") or 0),    step=0.1, format="%.1f")
        lug_to_lug  = sc2.number_input("Lug to Lug (mm)", value=float(watch.get("lug_to_lug_mm") or 0),  step=0.1, format="%.1f")
        thickness   = sc3.number_input("Thickness (mm)",   value=float(watch.get("thickness_mm") or 0),   step=0.1, format="%.1f")
        lug_width   = sc4.number_input("Lug Width (mm)",   value=float(watch.get("lug_width_mm") or 0),   step=0.5, format="%.1f")

        sc5, sc6, sc7, sc8 = st.columns(4)
        mat_idx      = CASE_MATERIALS.index(watch.get("case_material","")) if watch.get("case_material","") in CASE_MATERIALS else 0
        case_mat     = sc5.selectbox("Case Material", CASE_MATERIALS, index=mat_idx)
        color        = sc6.text_input("Dial Color", value=watch.get("color",""))
        solar        = sc7.checkbox("Solar", value=bool(watch.get("solar")))
        radio_sync   = sc8.checkbox("Radio Sync", value=bool(watch.get("radio_sync")))

        sc9, sc10, sc11 = st.columns(3)
        crys_idx      = CRYSTAL_TYPES.index(watch.get("crystal_type","")) if watch.get("crystal_type","") in CRYSTAL_TYPES else 0
        crystal_type  = sc9.selectbox("Crystal", CRYSTAL_TYPES, index=crys_idx)
        brac_idx      = BRACELET_MATERIALS.index(watch.get("bracelet_material","")) if watch.get("bracelet_material","") in BRACELET_MATERIALS else 0
        bracelet_mat  = sc10.selectbox("Bracelet Material", BRACELET_MATERIALS, index=brac_idx)
        water_res     = sc11.text_input("Water Resistance", value=watch.get("water_resistance",""), placeholder="100m, 200m, 10 bar…")

        sc12, sc13, sc14 = st.columns(3)
        movement_type = sc12.text_input("Movement Type", value=watch.get("movement_type",""), placeholder="Solar Quartz, Automatic…")
        jewel_count   = sc13.number_input("Jewels", value=int(watch.get("jewel_count") or 0), min_value=0, step=1,
                                          help="0 for quartz. Leave 0 if not applicable.")
        power_reserve = sc14.text_input("Power Reserve", value=watch.get("power_reserve",""), placeholder="40h, 6 months, Indefinite…")

        st.subheader("Purchase Costs")
        pc1, pc2, pc3 = st.columns(3)
        auction_jpy  = pc1.number_input("Auction JPY", value=float(watch.get("auction_price_jpy") or 0), step=100.0)
        auction_usd  = pc2.number_input("Auction USD", value=float(watch.get("auction_price_usd") or 0), step=0.01, format="%.2f")
        customs_usd  = pc3.number_input("Customs USD", value=float(watch.get("customs_duty_usd") or 0), step=0.01, format="%.2f")

        pc4, pc5, pc6 = st.columns(3)
        b_platform   = pc4.number_input("Buyee Platform JPY", value=float(watch.get("buyee_platform_jpy") or 500), step=100.0)
        b_inspection = pc5.number_input("Buyee Service JPY",  value=float(watch.get("buyee_inspection_jpy") or 500), step=100.0)
        b_domestic   = pc6.number_input("Domestic Ship JPY",  value=float(watch.get("domestic_shipping_jpy") or 900), step=100.0)

        pc7, pc8 = st.columns(2)
        intl_ship    = pc7.number_input("Intl Shipping USD (alloc.)", value=float(watch.get("intl_shipping_usd") or 0), step=0.01, format="%.2f")
        shipment_id  = pc8.text_input("Shipment ID", value=watch.get("shipment_id",""))

        st.subheader("Bench")
        labor_hrs    = st.number_input("Total Labor Hours", value=float(watch.get("total_labor_hours") or 0), step=0.25, format="%.2f")
        notes        = st.text_area("Notes / Journal", value=watch.get("notes",""), height=100)

        st.subheader("Flags")
        fl1, fl2 = st.columns(2)
        is_personal  = fl1.checkbox("Personal piece", value=bool(watch.get("is_personal")))
        current_status = fl2.selectbox(
            "Status (direct override)",
            VALID_STATUSES,
            index=VALID_STATUSES.index(watch["current_status"]) if watch["current_status"] in VALID_STATUSES else 0,
            help="Use Transitions tab to log stage changes with hours and notes. This is a raw override.",
        )

        submitted = st.form_submit_button("Save Changes", type="primary")

        if submitted:
            updates = {
                "brand": brand, "collection": collection, "reference": reference,
                "jdm_model": jdm_model, "serial": serial,
                "diameter_mm": diameter or None, "lug_to_lug_mm": lug_to_lug or None,
                "thickness_mm": thickness or None, "lug_width_mm": lug_width or None,
                "case_material": case_mat, "color": color,
                "solar": solar, "radio_sync": radio_sync,
                "crystal_type": crystal_type, "bracelet_material": bracelet_mat,
                "water_resistance": water_res, "movement_type": movement_type,
                "jewel_count": jewel_count or None, "power_reserve": power_reserve,
                "auction_price_jpy": auction_jpy or None, "auction_price_usd": auction_usd or None,
                "customs_duty_usd": customs_usd or None,
                "buyee_platform_jpy": b_platform, "buyee_inspection_jpy": b_inspection,
                "domestic_shipping_jpy": b_domestic,
                "intl_shipping_usd": intl_ship or None, "shipment_id": shipment_id or None,
                "total_labor_hours": labor_hrs, "notes": notes,
                "is_personal": is_personal,
            }
            # Strip None-equivalent zeros for optional numeric fields
            updates = {k: v for k, v in updates.items() if v != ""}
            try:
                api.update_watch(watch_id, updates)
                st.cache_data.clear()
                st.success("Saved.")
                st.rerun()
            except Exception as e:
                st.error(f"Save failed: {e}")

    # ── Danger zone ───────────────────────────────────────────────────────────
    st.divider()
    with st.expander("🗑️ Danger Zone", expanded=False):
        st.warning(
            "**Permanently deletes** this watch record and all its transitions and costs. "
            "S3 photos are left in place. This cannot be undone."
        )
        expected_ref = watch.get("reference", watch_id)
        confirm_del = st.text_input(
            f"Type **{expected_ref}** to enable deletion",
            key="delete_confirm",
            placeholder=expected_ref,
        )
        if st.button(
            "Delete this watch permanently",
            type="primary",
            disabled=(confirm_del != expected_ref),
            key="delete_watch_btn",
        ):
            try:
                api.delete_watch(watch_id)
                st.cache_data.clear()
                st.session_state.pop("selected_watch_id", None)
                st.success("Watch deleted.")
                log.info("watch deleted: %s", watch_id)
                st.switch_page("app.py")
            except Exception as e:
                st.error(f"Delete failed: {e}")


# ── Transitions ───────────────────────────────────────────────────────────────

with tab_transitions:
    if transitions:
        st.subheader("History")
        for t in sorted(transitions, key=lambda x: x.get("timestamp",""), reverse=True):
            # Prefer user-supplied event_date; fall back to insertion timestamp
            display_date = t.get("event_date") or t.get("timestamp","")[:10]
            frm = STATUS_LABELS.get(t.get("from_status",""), t.get("from_status",""))
            to  = STATUS_LABELS.get(t.get("to_status",""),   t.get("to_status",""))
            hrs = t.get("hours_spent", 0)
            hrs_str = f"  ·  {hrs}h" if hrs else ""
            st.markdown(f"**{display_date}** &nbsp; {frm} → **{to}**{hrs_str}")
            if t.get("notes"):
                st.caption(t["notes"])
            st.divider()
    else:
        st.info("No transitions logged yet.")

    # ── Close Sale ─────────────────────────────────────────────────────────────
    if watch["current_status"] not in ("sold", "shipped"):
        st.subheader("Close Sale")
        st.caption(
            "Records the sale, estimates or accepts platform fees, optionally logs ad spend, "
            "and calculates net profit — all in one step."
        )
        with st.form("close_sale"):
            cs1, cs2, cs3 = st.columns(3)
            close_sale_price = cs1.number_input(
                "Sale Price (USD) *", min_value=0.01, step=1.0, format="%.2f",
            )
            close_platform_idx = SALE_PLATFORMS.index("ebay") if "ebay" in SALE_PLATFORMS else 0
            close_platform = cs2.selectbox("Platform", SALE_PLATFORMS, index=close_platform_idx)
            close_sale_date = cs3.date_input("Sale Date", value=date_type.today())

            cs4, cs5, cs6 = st.columns(3)
            close_shipping = cs4.number_input(
                "Shipping Paid (USD)", value=6.0, min_value=0.0, step=0.50, format="%.2f",
            )
            close_label_source = cs4.selectbox(
                "Shipping Label Source",
                SHIPPING_LABEL_SOURCES,
                format_func=lambda s: SHIPPING_LABEL_SOURCE_LABELS.get(s, s),
            )
            close_fees = cs5.number_input(
                "Platform Fees (USD)",
                value=0.0, min_value=0.0, step=0.50, format="%.2f",
                help="Copy from eBay Seller Hub / Payments after the transaction settles. "
                     "eBay applies 15% on (sale price + buyer's sales tax) + $0.40 flat — "
                     "can't be pre-calculated without knowing the buyer's state.",
            )
            close_hours = cs6.number_input(
                "Hours (listing + packing)", value=0.0, min_value=0.0, step=0.25, format="%.2f",
            )

            cs7, cs8 = st.columns(2)
            close_ad_spend = cs7.number_input(
                "Ad Spend (USD)", value=0.0, min_value=0.0, step=1.0, format="%.2f",
                help="Any promoted listing or campaign cost. Added as an advertising cost before profit calc.",
            )
            close_ad_notes = cs8.text_input(
                "Ad Notes", placeholder="eBay 3-day promoted listing",
                help="Only used if Ad Spend > 0.",
            )

            close_notes = st.text_area("Notes", height=60, placeholder="Buyer location, any issues…")

            if st.form_submit_button("Close Sale 💰", type="primary"):
                if not close_sale_price:
                    st.error("Sale price is required.")
                else:
                    payload = {
                        "sale_price_usd":   close_sale_price,
                        "sale_platform":    close_platform,
                        "sale_date":        str(close_sale_date),
                        "event_date":       str(close_sale_date),
                        "shipping_cost_usd": close_shipping,
                        "shipping_label_source": close_label_source,
                        "hours_spent":      close_hours,
                        "notes":            close_notes,
                        "ad_spend_usd":     close_ad_spend,
                        "ad_notes":         close_ad_notes,
                    }
                    # Only send fees if user entered them (otherwise backend estimates)
                    if close_fees > 0:
                        payload["platform_fees_usd"] = close_fees

                    try:
                        result = api.close_sale(watch_id, payload)
                        st.cache_data.clear()
                        net = result.get("net_profit_usd", 0)
                        landed = result.get("total_landed_cost_usd", 0)
                        fees_actual = result.get("platform_fees_usd", 0)
                        st.success(
                            f"Sale closed.  |  "
                            f"Sale: **${result['sale_price_usd']:.2f}**  →  "
                            f"Fees: ${fees_actual:.2f}  ·  "
                            f"Shipping: ${result['shipping_cost_usd']:.2f}  ·  "
                            f"Landed: ${landed:.2f}  →  "
                            f"**Net: ${net:.2f}**"
                        )
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed: {e}")

        st.divider()

    st.subheader("Log Transition / Journal Entry")
    with st.form("add_transition"):
        current_idx = VALID_STATUSES.index(watch["current_status"]) if watch["current_status"] in VALID_STATUSES else 0
        tf1, tf2 = st.columns([2, 1])
        to_status = tf1.selectbox(
            "Status",
            VALID_STATUSES,
            index=current_idx,
            format_func=lambda s: STATUS_LABELS.get(s, s),
            help="Pick the same status to add a journal entry without changing stage.",
        )
        event_date = tf2.date_input(
            "Event date",
            value=date_type.today(),
            help="Change this to backdate the entry — e.g. work you did yesterday.",
        )
        hours_spent = st.number_input("Hours spent", min_value=0.0, step=0.25, format="%.2f")
        notes_t = st.text_area("Notes / Journal", height=100)
        if st.form_submit_button("Log", type="primary"):
            try:
                api.add_transition(watch_id, to_status, hours_spent, notes_t, str(event_date))
                st.cache_data.clear()
                st.success("Logged.")
                st.rerun()
            except Exception as e:
                st.error(f"Failed: {e}")

    # ── Edit Sale Record (corrections only, shown after Close Sale) ────────────
    if watch["current_status"] in ("sold", "shipped"):
        st.divider()
    with st.expander("Edit Sale Record", expanded=False):
        st.caption("Fill in once the watch sells. Saves price, platform, and calculates net profit.")

        # Parse existing sale_date if present
        existing_sale_date = date_type.today()
        if watch.get("sale_date"):
            try:
                from datetime import datetime
                existing_sale_date = datetime.strptime(watch["sale_date"][:10], "%Y-%m-%d").date()
            except Exception:
                pass

        with st.form("record_sale"):
            rs1, rs2 = st.columns(2)
            sale_price = rs1.number_input(
                "Sale Price (USD)",
                value=float(watch.get("sale_price_usd") or 0),
                min_value=0.0, step=1.0, format="%.2f",
            )
            plat_idx = SALE_PLATFORMS.index(watch.get("sale_platform","ebay")) if watch.get("sale_platform") in SALE_PLATFORMS else 0
            sale_platform = rs2.selectbox("Platform", SALE_PLATFORMS, index=plat_idx)

            rs3, rs4 = st.columns(2)
            sale_date_val = rs3.date_input("Sale Date", value=existing_sale_date)
            shipping_out = rs4.number_input(
                "Shipping Paid to Carrier (USD)",
                value=float(watch.get("shipping_cost_usd") or 6.0),
                min_value=0.0, step=0.50, format="%.2f",
                help="What you actually paid to ship to the buyer.",
            )
            label_idx = (
                SHIPPING_LABEL_SOURCES.index(watch["shipping_label_source"])
                if watch.get("shipping_label_source") in SHIPPING_LABEL_SOURCES else 0
            )
            label_source = rs4.selectbox(
                "Shipping Label Source",
                SHIPPING_LABEL_SOURCES,
                index=label_idx,
                format_func=lambda s: SHIPPING_LABEL_SOURCE_LABELS.get(s, s),
            )
            platform_fees = st.number_input(
                "Platform Fees (USD)",
                value=float(watch.get("platform_fees_usd") or 0),
                min_value=0.0, step=0.50, format="%.2f",
                help="eBay FVF charged after the sale. Leave 0 to let the backend estimate from config.",
            )

            if watch.get("net_profit_usd") is not None:
                st.metric("Recorded Net Profit", f"${watch['net_profit_usd']:,.2f}")

            if st.form_submit_button("Save Sale Data", type="primary"):
                sale_updates = {
                    "sale_price_usd": sale_price or None,
                    "sale_platform": sale_platform,
                    "sale_date": str(sale_date_val),
                    "shipping_cost_usd": shipping_out,
                    "shipping_label_source": label_source,
                    "platform_fees_usd": platform_fees or None,
                }
                sale_updates = {k: v for k, v in sale_updates.items() if v is not None}
                try:
                    api.update_watch(watch_id, sale_updates)
                    st.cache_data.clear()
                    st.success("Sale recorded.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed: {e}")


# ── Costs ─────────────────────────────────────────────────────────────────────

with tab_costs:
    if costs:
        total_add = sum(c.get("amount_usd", 0) for c in costs)
        st.subheader(f"Additional Costs  ·  Total: **${total_add:,.2f}**")

        costs_df = pd.DataFrame(costs)[["date", "category", "amount_usd", "notes"]].copy()
        costs_df["date"] = costs_df["date"].str[:10]
        st.dataframe(
            costs_df.rename(columns={
                "date": "Date", "category": "Category",
                "amount_usd": "Amount ($)", "notes": "Notes",
            }),
            column_config={"Amount ($)": st.column_config.NumberColumn("Amount ($)", format="%.2f")},
            hide_index=True, width='stretch',
        )

        # ── Edit / Delete a cost ──────────────────────────────────────────────
        st.subheader("Edit / Delete a Cost")
        sorted_costs = sorted(costs, key=lambda c: c.get("date", ""), reverse=True)
        cost_opts = {
            f"{c['date'][:10]}  ·  {c['category']}  ·  ${c.get('amount_usd', 0):.2f}"
            + (f"  —  {c['notes'][:40]}" if c.get("notes") else ""): c
            for c in sorted_costs
        }
        ec_label = st.selectbox("Select cost", list(cost_opts.keys()), key="cost_sel")
        ec = cost_opts[ec_label]

        with st.form("edit_cost_form"):
            ecc1, ecc2 = st.columns(2)
            edit_amt = ecc1.number_input(
                "Amount (USD)", value=float(ec.get("amount_usd", 0)),
                min_value=0.01, step=0.50, format="%.2f",
            )
            cat_idx  = COST_CATEGORIES.index(ec.get("category", "other")) \
                       if ec.get("category") in COST_CATEGORIES else 0
            edit_cat = ecc2.selectbox("Category", COST_CATEGORIES, index=cat_idx)
            edit_notes = st.text_area("Notes", value=ec.get("notes", ""), height=60)

            btn_save, btn_del = st.columns(2)
            if btn_save.form_submit_button("Save Changes", type="primary"):
                try:
                    api.update_cost(watch_id, ec["cost_id"],
                                    {"amount_usd": edit_amt, "category": edit_cat,
                                     "notes": edit_notes})
                    st.cache_data.clear()
                    st.success("Updated.")
                    log.info("cost updated %s/%s", watch_id, ec["cost_id"])
                    st.rerun()
                except Exception as e:
                    st.error(f"Update failed: {e}")
            if btn_del.form_submit_button("🗑️ Delete"):
                try:
                    api.delete_cost(watch_id, ec["cost_id"])
                    st.cache_data.clear()
                    st.success("Deleted.")
                    log.info("cost deleted %s/%s", watch_id, ec["cost_id"])
                    st.rerun()
                except Exception as e:
                    st.error(f"Delete failed: {e}")
    else:
        st.info("No additional costs logged.")

    st.divider()
    st.subheader("Add Cost")
    with st.form("add_cost"):
        cc1, cc2 = st.columns(2)
        amount   = cc1.number_input("Amount (USD)", min_value=0.01, step=0.50, format="%.2f")
        category = cc2.selectbox("Category", COST_CATEGORIES)
        notes_c  = st.text_area("Notes (part number, source, reason…)", height=80)
        if st.form_submit_button("Add", type="primary"):
            try:
                api.add_cost(watch_id, amount, category, notes_c)
                st.cache_data.clear()
                st.success("Added.")
                st.rerun()
            except Exception as e:
                st.error(f"Failed: {e}")


# ── Photos ────────────────────────────────────────────────────────────────────

with tab_photos:
    # Display existing photos (via listing report)
    try:
        report = api.get_listing_report(watch_id)
        existing_photos = report.get("photos", [])
    except Exception:
        existing_photos = []

    if existing_photos:
        current_thumb = watch.get("thumbnail_key", "")
        st.subheader(f"Uploaded Photos ({len(existing_photos)})")
        cols = st.columns(3)
        sorted_photos = sorted(existing_photos, key=lambda p: p["key"])
        for i, photo in enumerate(sorted_photos):
            with cols[i % 3]:
                filename = photo["key"].split("/")[-1]
                is_thumb  = photo["key"] == current_thumb
                caption   = f"{'⭐ ' if is_thumb else ''}{filename}"
                st.image(photo["url"], caption=caption, width='stretch')

        # ── Thumbnail picker ──────────────────────────────────────────────────
        st.divider()
        st.subheader("Thumbnail")
        st.caption("The thumbnail shows in the inventory list for quick visual identification.")
        photo_keys  = [p["key"] for p in sorted_photos]
        photo_names = [k.split("/")[-1] for k in photo_keys]
        thumb_opts  = ["— none —"] + photo_names
        current_idx = 0
        if current_thumb:
            thumb_name = current_thumb.split("/")[-1]
            if thumb_name in photo_names:
                current_idx = photo_names.index(thumb_name) + 1
        new_thumb_sel = st.selectbox("Thumbnail photo", thumb_opts, index=current_idx,
                                     key="thumb_picker")
        if st.button("Set thumbnail", key="set_thumb_btn"):
            if new_thumb_sel == "— none —":
                api.update_watch(watch_id, {"thumbnail_key": ""})
            else:
                idx = photo_names.index(new_thumb_sel)
                api.update_watch(watch_id, {"thumbnail_key": photo_keys[idx]})
            st.cache_data.clear()
            st.success("Thumbnail updated.")
            log.info("thumbnail set for %s → %s", watch_id, new_thumb_sel)
            st.rerun()
    else:
        st.info("No photos uploaded yet.")

    st.divider()
    st.subheader("Upload Photos")
    st.caption("Files are uploaded directly to S3 via presigned URLs. JPEG recommended.")

    uploaded_files = st.file_uploader(
        "Select files",
        accept_multiple_files=True,
        type=["jpg", "jpeg", "png"],
        key="photo_uploader",
    )

    if uploaded_files:
        st.write("Assign a slot to each file:")
        slot_map = {}
        for i, f in enumerate(uploaded_files):
            row_c1, row_c2, row_c3 = st.columns([2, 2, 1])
            row_c1.write(f"📎 {f.name}")
            default_slot_idx = min(i, len(PHOTO_SLOTS) - 1)
            slot_choice = row_c2.selectbox(
                "Slot",
                PHOTO_SLOTS + ["custom…"],
                index=default_slot_idx,
                key=f"slot_{i}",
                label_visibility="collapsed",
            )
            if slot_choice == "custom…":
                custom_name = row_c3.text_input("Name", key=f"custom_{i}", label_visibility="collapsed")
                slot_map[f.name] = custom_name.strip() or f"custom_{i:02d}"
            else:
                slot_map[f.name] = slot_choice

        if st.button("Upload All", type="primary"):
            progress = st.progress(0, text="Uploading…")
            errors = []
            for i, f in enumerate(uploaded_files):
                slot = slot_map[f.name]
                ext = f.name.rsplit(".", 1)[-1].lower() if "." in f.name else "jpg"
                filename = f"{slot}.{ext}"
                try:
                    upload_url = api.get_upload_url(watch_id, filename)
                    api.upload_photo(upload_url, f.getvalue(), f.type or "image/jpeg")
                    st.success(f"✓ {filename}")
                except Exception as e:
                    st.error(f"✗ {filename}: {e}")
                    errors.append(filename)
                progress.progress((i + 1) / len(uploaded_files), text=f"Uploading {filename}…")
            progress.empty()
            if not errors:
                st.rerun()


# ── Listing ───────────────────────────────────────────────────────────────────

with tab_listing:
    try:
        report = api.get_listing_report(watch_id)
    except Exception as e:
        st.error(f"Could not generate listing report: {e}")
        st.stop()

    pricing   = report.get("pricing", {})
    breakdown = pricing.get("breakdown", {})

    # cost_basis (landed + pre-sale bench costs) drives the ROI targets in pricing.py —
    # use the same figure here so the what-if calculator matches the backend numbers.
    landed     = breakdown.get(
        "total_cost_basis",
        watch.get("total_cost_basis_usd") or watch.get("total_landed_cost_usd") or 0,
    )
    labor_cost = breakdown.get("labor_cost", 0)
    labor_hrs  = watch.get("total_labor_hours") or 0

    # ── Feature pitch ─────────────────────────────────────────────────────────
    st.subheader("Pitch")
    st.caption("Why should someone buy this specific watch? Generated by Claude, edited by you, saved to the record.")

    pitch_key = f"pitch_ta_{watch_id}"
    # Seed session state from the watch record (only on first load for this watch)
    if pitch_key not in st.session_state:
        st.session_state[pitch_key] = watch.get("feature_pitch", "")

    pb1, pb2 = st.columns([1, 1])
    if pb1.button("Generate ✨", key="gen_pitch"):
        if "ANTHROPIC_API_KEY" not in st.secrets:
            st.error("ANTHROPIC_API_KEY not set in secrets.toml.")
        else:
            with st.spinner("Asking Claude…"):
                try:
                    generated = _generate_pitch(watch)
                    st.session_state[pitch_key] = generated
                    log.info("pitch generated for %s", watch_id)
                except Exception as e:
                    st.error(f"Generation failed: {e}")
                    log.error("pitch generation failed for %s: %s", watch_id, e)

    pitch_text = st.text_area(
        "Pitch text",
        value=st.session_state[pitch_key],
        height=120,
        key=pitch_key,
        label_visibility="collapsed",
    )

    if pb2.button("Save pitch 💾", key="save_pitch"):
        try:
            api.update_watch(watch_id, {"feature_pitch": pitch_text})
            st.cache_data.clear()
            st.success("Pitch saved.")
            log.info("pitch saved for %s", watch_id)
        except Exception as e:
            st.error(f"Save failed: {e}")

    st.divider()

    # ── Interactive pricing calculator ────────────────────────────────────────
    st.subheader("Pricing")

    # Adjustable parameters
    ac1, ac2, ac3 = st.columns(3)
    ad_rate  = ac1.number_input(
        "Ad rate %", min_value=0.0, max_value=20.0,
        value=float(breakdown.get("ad_rate_pct", 5)),
        step=0.5, format="%.1f",
        help="eBay Promoted Listings rate. Charged only on promoted sales; "
             "treat as a planning assumption.",
    )
    shipping_out = ac2.number_input(
        "Shipping to buyer ($)", min_value=0.0, max_value=50.0,
        value=6.0, step=0.50, format="%.2f",
    )
    min_profit = ac3.number_input(
        "Min profit floor ($)", min_value=0.0,
        value=float(breakdown.get("min_profit_usd", 20)),
        step=5.0, format="%.0f",
        help="Profit floor — protects against scaling too low on cheap pieces.",
    )

    # Fixed assumptions shown as caption
    ebay_fvf   = 0.15
    tax_blend  = 0.10
    pp_rate    = 0.029
    pp_flat    = 0.30
    labor_rate = 1.0  # matches config
    st.caption(
        f"Landed: **${landed:,.2f}**  ·  Labor: **${labor_cost:,.2f}**  ·  "
        f"eBay FVF: 15% × (1 + 10% tax blend)  ·  "
        f"Effective rate at {ad_rate:.1f}% ads: "
        f"**{(ebay_fvf * (1 + tax_blend) + ad_rate/100)*100:.1f}%**"
    )

    # Build tier rows dynamically
    tiers = [
        ("Fast",     20),
        ("Standard", 33),
        ("Patient",  50),
    ]
    tier_rows = []
    for label, roi_pct in tiers:
        e_price, target = _calc_ebay_price(
            landed, labor_hrs, labor_rate, shipping_out,
            ebay_fvf, tax_blend, ad_rate, roi_pct, min_profit,
        )
        d_price = _calc_direct_price(
            landed, labor_hrs, labor_rate, shipping_out,
            pp_rate, pp_flat, roi_pct, min_profit,
        )
        tier_rows.append({
            "Tier":          f"{label} ({roi_pct}% ROI)",
            "Target profit": f"${target:,.2f}",
            "eBay":          f"${e_price:,.2f}",
            "Direct / PP":   f"${d_price:,.2f}",
        })

    st.dataframe(pd.DataFrame(tier_rows), hide_index=True, width='stretch')

    st.divider()

    # ── Listing title ─────────────────────────────────────────────────────────
    st.subheader("Listing Title")
    st.code(report.get("title", ""), language=None)

    # ── Specs ─────────────────────────────────────────────────────────────────
    st.subheader("Specs")
    specs = report.get("specs", {})
    if specs:
        specs_df = pd.DataFrame(list(specs.items()), columns=["Field", "Value"])
        st.dataframe(specs_df, hide_index=True, width='content')

    # ── Description ───────────────────────────────────────────────────────────
    st.subheader("Description")
    st.code(report.get("description", ""), language=None)


# ── Admin ─────────────────────────────────────────────────────────────────────
# Every field already has a home in Edit/Transitions/Costs/Photos — this tab is for
# (1) a one-glance audit of the derived/computed fields for reconciling against eBay, and
# (2) a raw patch escape hatch for anything the specific forms don't cover well, instead of
# hand-editing DynamoDB.

_ADMIN_PATCH_FIELDS = [
    "sale_price_usd", "platform_fees_usd", "shipping_cost_usd", "shipping_label_source",
    "sale_platform", "sale_date", "auction_price_jpy", "auction_price_usd",
    "customs_duty_usd", "buyee_platform_jpy", "buyee_inspection_jpy",
    "domestic_shipping_jpy", "intl_shipping_usd", "shipment_id", "total_labor_hours",
    "thumbnail_key", "notes",
]
_ADMIN_NUMERIC_FIELDS = {
    "sale_price_usd", "platform_fees_usd", "shipping_cost_usd", "auction_price_jpy",
    "auction_price_usd", "customs_duty_usd", "buyee_platform_jpy", "buyee_inspection_jpy",
    "domestic_shipping_jpy", "intl_shipping_usd", "total_labor_hours",
}

with tab_admin:
    st.subheader("Cost Breakdown Audit")
    st.caption(
        "Every derived cost field in one place, for checking against real eBay/Buyee "
        "numbers during reconciliation. These aren't directly editable — fix the inputs "
        "(Edit tab, Costs tab, or the patch field below) and they recompute automatically."
    )

    audit_rows = [
        ("Landed (acquisition only)", watch.get("total_landed_cost_usd")),
        ("Pre-sale Costs (parts/repair)", watch.get("total_presale_costs_usd")),
        ("Cost Basis (landed + pre-sale)", watch.get("total_cost_basis_usd")),
        ("Additional Costs (all ADDCOST, any category)", watch.get("total_additional_costs_usd")),
        ("Sale Price", watch.get("sale_price_usd")),
        ("Platform Fees", watch.get("platform_fees_usd")),
        ("Shipping Cost", watch.get("shipping_cost_usd")),
        ("Net Profit", watch.get("net_profit_usd")),
    ]
    audit_df = pd.DataFrame(
        [(label, f"${v:,.2f}" if v is not None else "—") for label, v in audit_rows],
        columns=["Field", "Value"],
    )
    st.dataframe(audit_df, hide_index=True, width="stretch")

    label_src = watch.get("shipping_label_source") or "—"
    st.caption(
        f"Shipping label source: **{SHIPPING_LABEL_SOURCE_LABELS.get(label_src, label_src)}**"
    )

    st.divider()
    st.subheader("Quick Patch")
    st.caption(
        "Set any single field directly via the API — for corrections the other tabs don't "
        "cover well. Numeric-looking values are cast to numbers, true/false to booleans, "
        "everything else stored as text."
    )
    with st.form("admin_patch"):
        pf1, pf2 = st.columns([1, 2])
        patch_field = pf1.selectbox("Field", _ADMIN_PATCH_FIELDS)
        current_val = watch.get(patch_field)
        patch_value = pf2.text_input(
            "New value", value="" if current_val is None else str(current_val),
            help=f"Current value: {current_val!r}",
        )
        if st.form_submit_button("Patch field", type="primary"):
            val = patch_value.strip()
            if val.lower() in ("true", "false"):
                parsed = val.lower() == "true"
            else:
                try:
                    parsed = float(val) if val else None
                    if parsed is not None and parsed.is_integer():
                        parsed = int(parsed)
                except ValueError:
                    parsed = val

            if patch_field in _ADMIN_NUMERIC_FIELDS and not isinstance(parsed, (int, float, type(None))):
                st.error(
                    f"'{patch_field}' is a numeric field — '{patch_value}' isn't a number. "
                    "Nothing was sent."
                )
            else:
                try:
                    api.update_watch(watch_id, {patch_field: parsed})
                    st.cache_data.clear()
                    st.success(f"Patched {patch_field} → {parsed!r}")
                    log.info("admin patch %s.%s = %r", watch_id, patch_field, parsed)
                    st.rerun()
                except Exception as e:
                    st.error(f"Patch failed: {e}")

    with st.expander("Raw record (read-only)", expanded=False):
        st.json({k: v for k, v in watch.items() if k not in ("transitions", "additional_costs")})
