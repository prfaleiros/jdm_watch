import streamlit as st
import api
from constants import VALID_STATUSES, STATUS_LABELS, CASE_MATERIALS, CRYSTAL_TYPES, BRACELET_MATERIALS, BRANDS

st.set_page_config(page_title="New Watch", layout="wide", page_icon="⌚")
st.title("Add Watch")

with st.form("new_watch"):
    st.subheader("Identity")
    nc1, nc2, nc3 = st.columns(3)
    brand      = nc1.selectbox("Brand", BRANDS, index=0)
    collection = nc2.text_input("Collection", placeholder="Brightz, Spirit, xC…")
    reference  = nc3.text_input("Reference *", placeholder="7B24-0BH0")

    nc4, nc5 = st.columns(2)
    jdm_model = nc4.text_input("JDM Model", placeholder="SAGZ081")
    serial    = nc5.text_input("Serial")

    st.subheader("Specifications")
    sc1, sc2, sc3, sc4 = st.columns(4)
    diameter   = sc1.number_input("Diameter (mm)",    min_value=0.0, step=0.1, format="%.1f")
    lug_to_lug = sc2.number_input("Lug to Lug (mm)", min_value=0.0, step=0.1, format="%.1f")
    thickness  = sc3.number_input("Thickness (mm)",   min_value=0.0, step=0.1, format="%.1f")
    lug_width  = sc4.number_input("Lug Width (mm)",   min_value=0.0, step=0.5, format="%.1f")

    sc5, sc6, sc7, sc8 = st.columns(4)
    case_mat   = sc5.selectbox("Case Material", CASE_MATERIALS)
    color      = sc6.text_input("Dial Color", placeholder="Black, Silver, White…")
    solar      = sc7.checkbox("Solar powered")
    radio_sync = sc8.checkbox("Radio sync")

    sc9, sc10, sc11 = st.columns(3)
    crystal_type  = sc9.selectbox("Crystal", CRYSTAL_TYPES)
    bracelet_mat  = sc10.selectbox("Bracelet Material", BRACELET_MATERIALS)
    water_res     = sc11.text_input("Water Resistance", placeholder="100m, 200m…")

    sc12, sc13, sc14 = st.columns(3)
    movement_type = sc12.text_input("Movement Type", placeholder="Solar Quartz, Automatic…")
    jewel_count   = sc13.number_input("Jewels", min_value=0, step=1, help="0 for quartz.")
    power_reserve = sc14.text_input("Power Reserve", placeholder="40h, Indefinite…")

    st.subheader("Purchase Costs")
    pc1, pc2, pc3 = st.columns(3)
    auction_jpy = pc1.number_input("Auction JPY *", min_value=0.0, step=100.0)
    auction_usd = pc2.number_input("Auction USD (card charge) *", min_value=0.0, step=0.01, format="%.2f")
    customs_usd = pc3.number_input("Customs USD", min_value=0.0, step=0.01, format="%.2f")

    pc4, pc5, pc6 = st.columns(3)
    b_platform   = pc4.number_input("Buyee Platform JPY", value=500.0, step=100.0)
    b_inspection = pc5.number_input("Buyee Service JPY",  value=500.0, step=100.0,
                                    help="300 JPY for purchases before April 1 2026, 500 JPY after.")
    b_domestic   = pc6.number_input("Domestic Ship JPY",  value=900.0, step=100.0)
    buyee_fees_usd = st.number_input(
        "Buyee Fees USD (actual card charge)", min_value=0.0, step=0.01, format="%.2f",
        help="From the real Buyee invoice/card statement. Leave 0 if unknown yet — landed "
             "cost will estimate it using the auction's own JPY/USD rate, which can be off "
             "since Buyee fees are often charged separately at a different rate.",
    )

    pc7, pc8 = st.columns(2)
    intl_ship   = pc7.number_input("Intl Shipping USD (alloc.)", min_value=0.0, step=0.01, format="%.2f",
                                   help="Leave 0 if this watch belongs to a shipment — run allocation after creating the shipment.")
    shipment_id = pc8.text_input("Shipment ID", help="Link to an existing shipment for automatic allocation.")

    st.subheader("Status & Notes")
    fl1, fl2 = st.columns(2)
    current_status = fl1.selectbox(
        "Starting status",
        VALID_STATUSES,
        index=VALID_STATUSES.index("watching"),
        format_func=lambda s: STATUS_LABELS.get(s, s),
    )
    is_personal = fl2.checkbox("Personal piece (not for sale)")
    notes = st.text_area("Notes", height=80, placeholder="Condition notes, sourcing details…")

    submitted = st.form_submit_button("Create Watch", type="primary")

if submitted:
    if not reference:
        st.error("Reference is required.")
        st.stop()
    if not auction_jpy and not auction_usd:
        st.warning("Tip: add auction prices now so landed cost calculates correctly.")

    payload = {
        "brand": brand or "", "collection": collection, "reference": reference,
        "jdm_model": jdm_model, "serial": serial,
        "diameter_mm": diameter or None, "lug_to_lug_mm": lug_to_lug or None,
        "thickness_mm": thickness or None, "lug_width_mm": lug_width or None,
        "case_material": case_mat, "color": color,
        "solar": solar, "radio_sync": radio_sync,
        "crystal_type": crystal_type or None, "bracelet_material": bracelet_mat or None,
        "water_resistance": water_res or None, "movement_type": movement_type or None,
        "jewel_count": jewel_count or None, "power_reserve": power_reserve or None,
        "auction_price_jpy": auction_jpy or None, "auction_price_usd": auction_usd or None,
        "customs_duty_usd": customs_usd or None,
        "buyee_platform_jpy": b_platform, "buyee_inspection_jpy": b_inspection,
        "domestic_shipping_jpy": b_domestic, "buyee_fees_usd": buyee_fees_usd or None,
        "intl_shipping_usd": intl_ship or None,
        "shipment_id": shipment_id or None,
        "current_status": current_status,
        "is_personal": is_personal,
        "notes": notes,
    }

    try:
        result = api.create_watch(payload)
        new_id = result.get("watch_id")
        st.cache_data.clear()
        st.success(f"Watch created. ID: `{new_id}`  ·  Landed: ${result.get('total_landed_cost_usd', 0):.2f}")
        if st.button("Open Watch →"):
            st.session_state["selected_watch_id"] = new_id
            st.switch_page("pages/2_Watch.py")
    except Exception as e:
        st.error(f"Create failed: {e}")
