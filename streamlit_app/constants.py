VALID_STATUSES = [
    "watching", "bid_placed", "won", "in_transit_jp", "at_buyee",
    "in_transit_us", "received", "on_bench", "ready_to_list",
    "listed", "sold", "shipped",
]

STATUS_LABELS = {
    "watching":       "Watching",
    "bid_placed":     "Bid Placed",
    "won":            "Won",
    "in_transit_jp":  "In Transit JP",
    "at_buyee":       "At Buyee",
    "in_transit_us":  "In Transit US",
    "received":       "Received",
    "on_bench":       "On Bench",
    "ready_to_list":  "Ready to List",
    "listed":         "Listed",
    "sold":           "Sold",
    "shipped":        "Shipped",
}

# Lifecycle order for sorting
STATUS_ORDER = {s: i for i, s in enumerate(VALID_STATUSES)}

# Statuses that represent active (not archived) inventory
ACTIVE_STATUSES = [s for s in VALID_STATUSES if s not in ("sold", "shipped")]

PHOTO_SLOTS = [
    "01_dial",
    "02_caseback",
    "03_crown",
    "04_side",
    "05_bracelet",
    "06_clasp",
    "07_box_papers",
    "08_timestamp",
]

CASE_MATERIALS = ["", "Titanium", "Stainless Steel", "Gold-Tone", "Two-Tone", "Resin", "Other"]

CRYSTAL_TYPES = ["", "Hardlex", "Sapphire", "Mineral", "Acrylic", "Other"]

BRACELET_MATERIALS = ["", "Titanium", "Stainless Steel", "Resin", "Leather", "NATO", "Rubber", "Other"]

COST_CATEGORIES = ["part", "consumable", "tool", "shipping", "advertising", "other"]

# Categories treated as pre-sale (bench/repair) cost basis vs. everything else — must match
# PRESALE_CATEGORIES in lambdas/shared/python/costs.py.
PRESALE_COST_CATEGORIES = {"part", "consumable", "tool"}

SHIPPING_LABEL_SOURCES = ["platform", "external"]
SHIPPING_LABEL_SOURCE_LABELS = {
    "platform": "Platform-provided label",
    "external": "External (e.g. stamps.com)",
}

AD_CAMPAIGN_PLATFORMS = ["ebay_offsite", "reddit", "other"]
AD_CAMPAIGN_PLATFORM_LABELS = {
    "ebay_offsite": "eBay Offsite Ads",
    "reddit": "Reddit promotion",
    "other": "Other",
}

# Best-effort collection -> market tier, used to group sold pieces in Financials.
# Deliberately NOT price-derived — a restored/flipped piece's sale price doesn't reflect
# where the collection actually sits in the lineup. Paulo-confirmed: Seiko 5/Spirit/Selection
# = Entry, Brightz = Mid, Astron = Top. Everything else below is a best-effort guess based on
# each collection's general market position — correct freely, this is meant to be edited.
# Lookup is case-insensitive; unknown collections fall back to "Unclassified" rather than
# being silently dropped or misclassified.
COLLECTION_TIERS = {
    # Entry — confirmed
    "seiko 5": "Entry",
    "5": "Entry",
    "spirit": "Entry",
    "selection": "Entry",
    # Entry — best guess
    "exceline": "Entry",
    "lukia": "Entry",
    "alba": "Entry",
    "harmony": "Entry",
    "xc": "Entry",
    # Mid — confirmed
    "brightz": "Mid",
    # Mid — best guess
    "5 sports": "Mid",
    "dolce": "Mid",
    "lord matic": "Mid",
    "presage": "Mid",
    "prospex": "Mid",
    # Top — confirmed. Paulo: "the only one in the lineup that belongs there" — no other
    # guessed top-tier entries; add one explicitly if that changes.
    "astron": "Top",
}

SALE_PLATFORMS = ["ebay", "reddit", "direct", "other"]

BRANDS = ["", "Seiko", "Citizen", "Casio", "Orient", "Other"]

# Caliber-level editorial hints used by the pitch generator.
# Key = caliber prefix (matched from the start of the reference string, case-insensitive).
# Value = the reframing note passed to Claude — factual, no marketing spin.
CALIBER_HINTS = {
    "7T32": "The alarm hand doubles as a GMT/dual time zone indicator — frame it as a second time zone function, not an alarm. Two time zones, zero added complexity.",
    "7B22": "Solar-powered radio-control accuracy with perpetual calendar convenience — a true 'set it and forget it' JDM Seiko engine.",
    "7B24": "The sweet spot of Seiko radio-solar: multi-band world time, perpetual calendar, and usually WWVB support, making it especially attractive for US buyers.",
    "7B42": "Slim, practical radio-solar reliability with perpetual calendar — a great everyday JDM quartz, though typically Japan radio only.",
    "8B82": "Feature-rich radio-solar chronograph movement with perpetual calendar and world-time capability — a serious tech-forward Seiko caliber.",
    "8B92": "Premium radio-solar chronograph with 1/5-second timing, perpetual calendar, and world-time functionality — one of Seiko's strongest modern quartz chrono packages.",
    "7S26": "Seiko's legendary no-nonsense automatic workhorse — rugged, simple, affordable, and trusted across millions of watches.",
    "7S36": "A slightly upgraded 7S-family automatic with extra jewels — same durable workhorse character with a little more mechanical refinement.",
    "4R26": "Reliable modern Seiko automatic platform with hacking/hand-winding convenience over the older 7S family.",
    "4R36": "The modern enthusiast favorite: automatic, hacking, hand-winding, day-date, and widely serviceable.",
    "8F56": "Perpetual calendar quartz. Set it once; it tracks month length and leap years on its own until 2100.",
    "8J55": "Spring Drive — a mechanical movement regulated by a tri-synchro glide spring instead of a traditional escapement. True sweeping seconds, virtually no tick.",
    "8F32": "Analog solar quartz with radio control. Light powers the movement indefinitely; the radio signal keeps it atomic-accurate.",
    "7N43": "Dependable quartz with day-date practicality — thin, accurate, low-maintenance, and ideal for vintage/JDM daily wear.",
    "5B21": "Battery-powered radio-controlled quartz with perpetual calendar precision — rare, unusual, and more sophisticated than it first appears.",
    "H851": "Eco-Drive solar — the dial itself harvests light and stores energy in a capacitor. Fully charged, it runs for months in complete darkness.",
    "H820": "Eco-Drive with perpetual calendar and world time. Solar powered, self-correcting calendar, 26 time zones on the dial.",
    "E820": "Satellite Wave — syncs to GPS satellites anywhere on Earth. No radio transmitter dependency; position-agnostic timekeeping.",
}
