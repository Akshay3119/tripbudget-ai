"""Apply explicit, reproducible field reviews to captured official-source text, never LLM-extracted truth."""

import hashlib
import json
import re
from pathlib import Path

from tripbudget.schemas import utcnow

# Exact brief source spans inspected during construction; no promotion from mere source-ID membership.
REVIEWS = {
    "phl-pma": ("pma", r"Adults\s+\$30\b", 3000),
    "dc-natural-history": ("natural-history", r"Admission is free\s*\.", 0),
    "dc-american-history": ("american-history", r"Free admission", 0),
    "nyc-ferry": ("ferry", r"free service between Staten Island and Lower Manhattan", 0),
    "phl-liberty-bell": ("liberty-bell", r"Admission is FREE\s*\.", 0),
}


def main():
    file = Path("corpus/catalog.json")
    data = json.loads(file.read_text())
    sources = {x["source_id"]: x for x in data["sources"]}
    for source in sources.values():
        source["excerpt"] = " ".join(source["excerpt"].split()[:12])
    applied = []
    for activity in data["activities"]:
        if activity["id"] not in REVIEWS:
            continue
        source_id, pattern, cents = REVIEWS[activity["id"]]
        text = Path(".runtime/source-downloads", source_id + ".txt").read_text()
        match = re.search(pattern, text)
        if not match or sources[source_id]["fetch_status"] != "OK":
            raise SystemExit("Source span missing; refusing to mark reviewed: " + source_id)
        activity.update(
            {
                "evidence_state": "VERIFIED_SNAPSHOT",
                "reviewed_fields": ["price_cents"],
                "price_cents": cents,
                "review_quote": match.group(0),
                "reviewed_by": "Codex-assisted explicit source-span inspection",
                "reviewed_at": utcnow().isoformat(),
                "review_source_sha256": sources[source_id]["sha256"],
                "price_note": "Posted adult/general admission or ferry service charge; extra services excluded. "
                "Any unquoted mandatory checkout fees remain a planning assumption.",
            }
        )
        applied.append(activity["id"])
    data["version"] = data["version"].split("-r")[0] + "-r1"
    file.write_text(json.dumps(data, indent=2))
    manifest_file = Path("corpus/manifest.json")
    manifest = json.loads(manifest_file.read_text())
    manifest.update(
        {
            "catalog_sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
            "version": data["version"],
            "reviewed_price_facts": applied,
        }
    )
    manifest_file.write_text(json.dumps(manifest, indent=2))
    print("Source-span-reviewed price facts:", ", ".join(applied))


if __name__ == "__main__":
    main()
