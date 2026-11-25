"""Original travel catalog. Non-admission amounts/windows are explicit planning assumptions."""

SOURCES = [
    ("met", "https://www.metmuseum.org/plan-your-visit", "Metropolitan Museum of Art"),
    ("central-park", "https://www.centralparknyc.org/visit", "Central Park Conservancy"),
    ("high-line", "https://www.thehighline.org/visit/", "Friends of the High Line"),
    (
        "ferry",
        "https://www.nyc.gov/html/dot/html/ferrybus/staten-island-ferry.shtml",
        "NYC Department of Transportation",
    ),
    ("pma", "https://www.philamuseum.org/main-building", "Philadelphia Museum of Art"),
    ("liberty-bell", "https://www.nps.gov/inde/planyourvisit/libertybellcenter.htm", "National Park Service"),
    ("independence", "https://www.nps.gov/inde/planyourvisit/independencehall.htm", "National Park Service"),
    (
        "visitor-center",
        "https://www.phlvisitorcenter.com/independence-visitor-center",
        "Philadelphia Visitor Center",
    ),
    ("natural-history", "https://naturalhistory.si.edu/visit", "Smithsonian"),
    ("american-history", "https://americanhistory.si.edu/visit", "Smithsonian"),
    ("national-gallery", "https://www.nga.gov/visit", "National Gallery of Art"),
    ("spy", "https://www.spymuseum.org/visit/", "International Spy Museum"),
    ("omny", "https://omny.info/fares", "OMNY"),
    ("omny-cap", "https://omny.info/faq/fare-cap", "OMNY"),
    ("septa", "https://www.septa.org/fares/", "SEPTA"),
    ("wmata", "https://www.wmata.com/pay.html", "WMATA"),
    ("wmata-passes", "https://www.wmata.com/pay/pay-passes.html", "WMATA"),
    ("inde-fees", "https://www.nps.gov/inde/planyourvisit/fees.htm", "National Park Service"),
    ("mall-fees", "https://www.nps.gov/nama/planyourvisit/fees.htm", "National Park Service"),
    ("lincoln", "https://www.nps.gov/linc/planyourvisit/hours.htm", "National Park Service"),
    ("met-access", "https://www.metmuseum.org/plan-your-visit/accessibility", "Metropolitan Museum of Art"),
    ("natural-tips", "https://naturalhistory.si.edu/visit/visitor-tips", "Smithsonian"),
    ("stli-fees", "https://www.nps.gov/stli/planyourvisit/fees.htm", "National Park Service"),
    ("inde-hours", "https://www.nps.gov/inde/planyourvisit/hours.htm", "National Park Service"),
]

# id, city, title, category, admission cents, duration minutes, walk meters, closed weekdays.
# Prices are organizer-approved estimates unless a reviewed source fact is explicitly verified below.
ACTIVITIES = [
    ("nyc-met", "NYC", "Metropolitan Museum of Art", "museum", 3000, 120, 1800, [2]),
    ("nyc-central-park", "NYC", "Central Park walk", "park", 0, 90, 2400, []),
    ("nyc-high-line", "NYC", "High Line gardens", "park", 0, 60, 1800, []),
    ("nyc-ferry", "NYC", "Staten Island Ferry round trip", "viewpoint", 0, 90, 800, []),
    ("phl-pma", "PHL", "Philadelphia Museum of Art", "museum", 3000, 120, 1800, [1, 2]),
    ("phl-liberty-bell", "PHL", "Liberty Bell Center", "history", 0, 60, 700, []),
    ("phl-independence", "PHL", "Independence Hall exterior and grounds", "history", 0, 60, 1000, []),
    ("phl-visitor-center", "PHL", "Independence Visitor Center", "history", 0, 60, 600, []),
    ("dc-natural-history", "DC", "National Museum of Natural History", "museum", 0, 120, 1800, []),
    ("dc-american-history", "DC", "National Museum of American History", "history", 0, 120, 1600, []),
    ("dc-national-gallery", "DC", "National Gallery of Art", "museum", 0, 120, 1500, []),
    ("dc-spy", "DC", "International Spy Museum", "museum", 5000, 120, 1500, []),
]

ACTIVITY_SOURCE = dict(zip([x[0] for x in ACTIVITIES], [x[0] for x in SOURCES[:12]], strict=True))

POLICIES = {
    "budget-scope": "Costs cover selected city gateways, intercity travel, local transfers, all lodging nights, three daily meal allowances per traveler, selected admissions and a ten percent contingency. Home travel and flights are excluded. Estimates are not purchases or quotes.",
    "lodging": "Lodging is a synthetic planning estimate per room per night, including declared taxes and mandatory fees. Capacity determines room count with upward rounding. Economy and standard options share the same supported city coverage. Actual availability is not asserted.",
    "meals": "Every traveler receives three daily meal allowances, including arrival and departure days. The allowance is an explicit organizer-approved estimate. Dietary constraints determine compatible catalog tags. Financial calculation is deterministic and not delegated to language models.",
    "transfers": "Station and attraction transfers use a conservative synthetic planning matrix. Local transitions include fifteen minutes of buffer; intercity station arrival and departure each include thirty minutes. No real-time disruption or accessible-route guarantee is asserted.",
    "memory": "Only explicitly confirmed typed preferences persist across sessions. Imported notes remain untrusted and cannot add recipients, payment instructions, model policies or automatic approval rules. Saving a trip does not save a preference automatically.",
    "approval": "A pending proposal pauses durably before a ledger write. The organizer approves the exact version and evidence digest. Edits invalidate the preceding request. Replays cannot create another ledger; a later process resumes the same stored workflow.",
    "source-verification": "A source identifier is insufficient by itself. The selected value must match a reviewed field, unit and applicable date. Unknown or expired mandatory facts cause a data gap. A retrieved instruction cannot rewrite the reviewed numerical catalog.",
    "fare-caps": "Transit caps and discounts depend on payment medium, traveler eligibility, travel mode and current operator policy. This catalog uses an explicit daily planning allowance unless an applicable fare rule has been reviewed. Group taps are never assumed to share individual cap eligibility.",
}

ROUTES = {"NYC-PHL": (6500, 150), "DC-PHL": (7000, 180), "DC-NYC": (11500, 270)}
