import streamlit as st
import pandas as pd
import api

st.set_page_config(page_title="Shipment", layout="wide", page_icon="⌚")
st.title("Shipment")
st.caption("Group watches into a Buyee shipment and allocate international shipping costs by auction price weight.")

tab_create, tab_allocate = st.tabs(["Create Shipment", "Allocate Costs"])


# ── Create ────────────────────────────────────────────────────────────────────

with tab_create:
    st.subheader("New Shipment")
    with st.form("create_shipment"):
        cc1, cc2 = st.columns(2)
        total_cost_usd = cc1.number_input(
            "Total cost USD (intl shipping + customs charged to card) *",
            min_value=0.01, step=0.01, format="%.2f",
        )
        total_cost_jpy = cc2.number_input(
            "Total cost JPY (optional reference)",
            min_value=0.0, step=100.0,
        )
        cc3, cc4 = st.columns(2)
        weight_g   = cc3.number_input("Weight (g)", min_value=0.0, step=10.0)
        dimensions = cc4.text_input("Dimensions", placeholder="31x34x12cm")

        cc5, cc6 = st.columns(2)
        carrier   = cc5.selectbox("Carrier", ["DHL", "EMS", "SAL", "Other"], index=0)
        ship_date = cc6.date_input("Ship date (approx.)")

        notes_s = st.text_area("Notes", height=60, placeholder="Buyee invoice number, tracking…")

        st.info(
            "After creating, go to the **Allocate Costs** tab: add the watches in this shipment "
            "and click Allocate to distribute international shipping proportionally."
        )
        if st.form_submit_button("Create Shipment", type="primary"):
            payload = {
                "total_cost_usd": total_cost_usd,
                "total_cost_jpy": total_cost_jpy or None,
                "weight_g": weight_g or None,
                "dimensions": dimensions,
                "carrier": carrier,
                "ship_date": str(ship_date),
                "notes": notes_s,
            }
            try:
                result = api.create_shipment(payload)
                ship_id = result.get("shipment_id")
                st.cache_data.clear()
                st.success(f"Shipment created. ID: `{ship_id}`")
                st.session_state["active_shipment_id"] = ship_id
            except Exception as e:
                st.error(f"Failed: {e}")


# ── Allocate ──────────────────────────────────────────────────────────────────

with tab_allocate:
    st.subheader("Allocate Shipping Costs")
    st.caption(
        "Enter the shipment ID and link watches to it. Each watch's intl_shipping_usd will be "
        "set proportionally based on auction price in JPY."
    )

    shipment_id = st.text_input(
        "Shipment ID",
        value=st.session_state.get("active_shipment_id", ""),
        placeholder="e.g. a1b2c3d4",
    )

    # Load watches and let user pick which belong to this shipment
    try:
        all_watches = api.list_watches()
    except Exception as e:
        st.error(f"Could not load watches: {e}")
        st.stop()

    # Show watches not yet linked to any shipment (or already linked to this one)
    eligible = [
        w for w in all_watches
        if not w.get("is_personal") and (
            not w.get("shipment_id") or w.get("shipment_id") == shipment_id
        )
    ]

    if not eligible:
        st.info("No unlinked business watches found.")
    else:
        eligible_labels = {
            f"{w['brand']} {w['collection']} {w['reference']}": w["watch_id"]
            for w in eligible
        }
        selected_labels = st.multiselect(
            "Watches in this shipment",
            list(eligible_labels.keys()),
            default=[
                f"{w['brand']} {w['collection']} {w['reference']}"
                for w in eligible
                if w.get("shipment_id") == shipment_id
            ],
        )
        selected_ids = [eligible_labels[l] for l in selected_labels]

        if selected_ids:
            st.caption(f"{len(selected_ids)} watches selected.")

        if st.button("Link & Allocate", type="primary", disabled=not (shipment_id and selected_ids)):
            errors = []

            # Link watches to shipment
            with st.spinner("Linking watches…"):
                for wid in selected_ids:
                    try:
                        api.update_watch(wid, {"shipment_id": shipment_id})
                    except Exception as e:
                        errors.append(f"Link {wid}: {e}")

            # Run allocation
            if not errors:
                with st.spinner("Allocating…"):
                    try:
                        result = api.allocate_shipment(shipment_id)
                        st.cache_data.clear()
                        st.success("Allocation complete.")
                        if "allocations" in result:
                            alloc_df = pd.DataFrame(result["allocations"])
                            st.dataframe(alloc_df, hide_index=True, width='stretch')
                    except Exception as e:
                        errors.append(f"Allocate: {e}")

            for err in errors:
                st.error(err)
