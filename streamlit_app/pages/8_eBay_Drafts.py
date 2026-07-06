import io
import csv
import streamlit as st
import api
from constants import STATUS_LABELS

st.set_page_config(page_title="eBay Draft Export", layout="wide", page_icon="⌚")
st.title("eBay Draft Export")
st.caption("Generate an eBay bulk-upload CSV to pre-populate draft listings.")

ELIGIBLE_STATUSES = {"in_transit_us", "received", "ready_to_list"}
CATEGORY_ID = "31387"

# ── Fixed header rows (rows 1-4) and column header (row 5) ───────────────────

_FIXED_ROWS = [
    ["#INFO", "Version=0.0.2", "Template= eBay-draft-listings-template_US",
     "", "", "", "", "", "", "", ""],
    ["#INFO Action and Category ID are required fields. 1) Set Action to Draft "
     "2) Please find the category ID for your listings here: "
     "https://pages.ebay.com/sellerinformation/news/categorychanges.html",
     "", "", "", "", "", "", "", "", "", ""],
    ["#INFO After you've successfully uploaded your draft from the Seller Hub "
     "Reports tab, complete your drafts to active listings here: "
     "https://www.ebay.com/sh/lst/drafts",
     "", "", "", "", "", "", "", "", "", ""],
    ["#INFO", "", "", "", "", "", "", "", "", "", ""],
]

_HEADER_ROW = [
    "Action(SiteID=US|Country=US|Currency=USD|Version=1193|CC=UTF-8)",
    "Custom label (SKU)",
    "Category ID",
    "Title",
    "UPC",
    "Price",
    "Quantity",
    "Item photo URL",
    "Condition ID",
    "Description",
    "Format",
]


def _to_html(description: str) -> str:
    """Convert the plain-text listing description to eBay-friendly HTML.

    The first line is the title (already in the Title column), so it is skipped.
    Section headers are ALL-CAPS lines; bullet lines start with '•'.
    """
    lines = description.split("\n")[1:]  # drop title line
    html = []
    in_list = False

    for line in lines:
        s = line.strip()
        if not s:
            if in_list:
                html.append("</ul>")
                in_list = False
            continue
        if s.startswith("•"):
            if not in_list:
                html.append("<ul>")
                in_list = True
            html.append(f"<li>{s[1:].strip()}</li>")
        elif s == s.upper() and len(s) > 3:   # section header (ALL CAPS)
            if in_list:
                html.append("</ul>")
                in_list = False
            html.append(f"<p><b>{s}</b></p>")
        else:
            if in_list:
                html.append("</ul>")
                in_list = False
            html.append(f"<p>{s}</p>")

    if in_list:
        html.append("</ul>")

    return "".join(html)


# ── Watch selection ───────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def _load_watches():
    return api.list_watches()


try:
    all_watches = _load_watches()
except Exception as e:
    st.error(f"Failed to load watches: {e}")
    st.stop()

eligible = [
    w for w in all_watches
    if w.get("current_status") in ELIGIBLE_STATUSES and not w.get("is_personal")
]

if not eligible:
    st.info("No eligible watches (in transit US / received / ready to list).")
    st.stop()


def _label(w):
    status = STATUS_LABELS.get(w.get("current_status", ""), w.get("current_status", ""))
    return f"[{w['watch_id']}] {w.get('brand', '')} {w.get('collection', '')} {w.get('reference', '')} · {status}"


watch_opts = {w["watch_id"]: _label(w) for w in eligible}

selected_ids = st.multiselect(
    "Select watches to include",
    list(watch_opts.keys()),
    format_func=lambda wid: watch_opts[wid],
)

if not selected_ids:
    st.info("Select at least one watch to generate the CSV.")
    st.stop()

# ── Generate ──────────────────────────────────────────────────────────────────

if st.button(f"Generate CSV for {len(selected_ids)} watch(es)", type="primary"):
    data_rows = []
    errors = []
    progress = st.progress(0, text="Fetching listing data…")

    for i, wid in enumerate(selected_ids):
        progress.progress(i / len(selected_ids), text=f"Fetching {watch_opts[wid]}…")
        try:
            report = api.get_listing_report(wid)
        except Exception as e:
            errors.append(f"{watch_opts[wid]}: {e}")
            continue

        title = report.get("title", "")
        description_html = _to_html(report.get("description", ""))
        patient = report.get("pricing", {}).get("patient", {})
        price = patient.get("ebay_price", "")
        photos = report.get("photos", [])
        photo_url = photos[0]["url"] if photos else ""

        data_rows.append([
            "Draft",
            wid,
            CATEGORY_ID,
            title,
            "",                                    # UPC
            f"{price:.2f}" if price else "",
            "1",
            photo_url,
            "",                                    # Condition ID
            description_html,
            "FixedPrice",
        ])

    progress.progress(1.0, text="Done!")
    progress.empty()

    for err in errors:
        st.error(err)

    if data_rows:
        buf = io.StringIO()
        writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
        for row in _FIXED_ROWS:
            writer.writerow(row)
        writer.writerow(_HEADER_ROW)
        for row in data_rows:
            writer.writerow(row)

        st.download_button(
            f"Download eBay drafts CSV ({len(data_rows)} listing(s))",
            buf.getvalue().encode("utf-8"),
            file_name="ebay_drafts.csv",
            mime="text/csv",
        )

        if len(data_rows) < len(selected_ids):
            st.warning(f"{len(selected_ids) - len(data_rows)} watch(es) failed — see errors above.")
        else:
            st.success(f"Ready. Upload to Seller Hub → Reports → Upload.")
