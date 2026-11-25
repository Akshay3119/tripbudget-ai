"""Fetch official source snapshots; build original paraphrased travel documents and a real vector index."""

import asyncio
import hashlib
import json
import re
import sys
from datetime import timedelta
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "corpus"))
from seed import ACTIVITIES, ACTIVITY_SOURCE, POLICIES, ROUTES, SOURCES  # noqa: E402
from tripbudget.persistence import digest  # noqa: E402
from tripbudget.schemas import utcnow  # noqa: E402
from tripbudget.settings import Settings  # noqa: E402


async def main():
    settings = Settings()
    raw_dir = ROOT / ".runtime" / "source-downloads"
    raw_dir.mkdir(parents=True, exist_ok=True)
    now = utcnow()
    snapshots, documents = [], []
    async with httpx.AsyncClient(timeout=25, follow_redirects=True, trust_env=False) as client:
        for source_id, url, publisher in SOURCES:
            try:
                response = await client.get(
                    url, headers={"User-Agent": "TripBudgetAI/1.0 academic source verification"}
                )
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "html.parser")
                for element in soup(["script", "style", "nav", "header", "footer"]):
                    element.decompose()
                text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
                (raw_dir / (source_id + ".txt")).write_text(text)
                sha = hashlib.sha256(response.content).hexdigest()
                # At most a short exact excerpt; full fetched material remains ignored, not distributed.
                match = re.search(r"(?:Admission|admission|Adults|free|Free|Hours|hours).{0,110}", text)
                excerpt = " ".join((match.group(0) if match else text).split()[:12])
                snapshots.append(
                    {
                        "source_id": source_id,
                        "url": url,
                        "publisher": publisher,
                        "fetched_at": now.isoformat(),
                        "expires_at": (now + timedelta(days=7)).isoformat(),
                        "sha256": sha,
                        "excerpt": excerpt,
                        "fetch_status": "OK",
                        "review": "machine-fetched; individual facts separately reviewed",
                    }
                )
                print(source_id, "OK", len(text), flush=True)
            except httpx.HTTPError as exc:
                snapshots.append(
                    {
                        "source_id": source_id,
                        "url": url,
                        "publisher": publisher,
                        "fetch_status": "UNAVAILABLE",
                        "error": type(exc).__name__,
                        "fetched_at": now.isoformat(),
                        "expires_at": now.isoformat(),
                        "sha256": "",
                        "excerpt": "",
                        "review": "not verified",
                    }
                )
                print(source_id, "UNAVAILABLE", flush=True)
    activities = []
    for identifier, city, title, category, price, duration, walk, closed in ACTIVITIES:
        source_id = ACTIVITY_SOURCE[identifier]
        # Default all assumptions to estimates. No keyword/LLM extraction silently promotes them.
        activity = {
            "id": identifier,
            "city": city,
            "title": title,
            "category": category,
            "price_cents": price,
            "duration_minutes": duration,
            "walk_meters": walk,
            "closed_weekdays": closed,
            "open_hour": 10,
            "close_hour": 17,
            "source_id": source_id,
            "evidence_state": "USER_ESTIMATE",
            "observed_at": now.isoformat(),
            "expires_at": (now + timedelta(days=7)).isoformat(),
            "price_note": "Explicit all-in planning amount; organizer confirmation required",
            "schedule_state": "USER_ESTIMATE",
            "reviewed_fields": [],
            "closed_dates": ["12-25", "01-01"] if category == "museum" else [],
        }
        activities.append(activity)
        for suffix, paragraph in {
            "overview": f"{title} is a {category} option in {city}. Its catalog ID is {identifier}. The proposed visit lasts {duration} minutes and includes an estimated {walk} meters of walking. This is a scoped group travel option, not a reservation or an accessible-route guarantee.",
            "price": f"Admission planning value for {title} in {city} is {price} USD cents per adult participant. Unless a reviewed fact explicitly marks it verified, this is a confirmed user estimate. The broker supplies this value by ID; a model cannot change it by citing different text.",
            "schedule": f"The planning window for {title} in {city} is 10:00 to 17:00 America/New_York. Proposed duration is {duration} minutes. Closed weekday indices are {closed}. This conservative planning assumption still requires date and holiday checking; it does not guarantee entry or tickets.",
        }.items():
            documents.append(
                {
                    "id": identifier + ":" + suffix,
                    "source_id": source_id,
                    "activity_id": identifier,
                    "city": city,
                    "text": paragraph,
                    "kind": suffix,
                    "trusted_numeric_source": False,
                }
            )
    for source in snapshots:
        documents.append(
            {
                "id": "source:" + source["source_id"],
                "source_id": source["source_id"],
                "activity_id": "",
                "city": "ALL",
                "kind": "source_metadata",
                "text": f"Official publisher {source['publisher']} has reference URL {source['url']}. Fetch status is {source['fetch_status']}. This record establishes source provenance only; numerical facts require separate field verification and current applicability.",
                "trusted_numeric_source": False,
            }
        )
    for name, text in POLICIES.items():
        documents.append(
            {
                "id": "policy:" + name,
                "source_id": "project-policy",
                "activity_id": "",
                "city": "ALL",
                "kind": "project_policy",
                "text": text,
                "trusted_numeric_source": False,
            }
        )
    catalog = {
        "routes": {
            key: {
                "price_cents": price,
                "duration_minutes": minutes,
                "evidence_state": "USER_ESTIMATE",
                "expires_at": (now + timedelta(days=7)).isoformat(),
                "note": "Synthetic all-in station-to-station planning assumption; no live inventory",
            }
            for key, (price, minutes) in ROUTES.items()
        },
        "version": now.strftime("%Y%m%dT%H%M%SZ"),
        "as_of": now.isoformat(),
        "activities": activities,
        "sources": snapshots,
        "documents": documents,
        "rights": "Original summaries and brief source excerpts. Source copyrights retained by publishers.",
    }
    target = ROOT / "corpus" / "catalog.json"
    target.write_text(json.dumps(catalog, indent=2))
    (ROOT / "corpus" / "manifest.json").write_text(
        json.dumps(
            {
                "catalog_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                "version": catalog["version"],
                "source_count": len(snapshots),
                "chunk_count": len(documents),
                "embedding_model": "BAAI/bge-small-en-v1.5",
                "dimension": 384,
            },
            indent=2,
        )
    )
    print("Catalog", catalog["version"], "documents", len(documents), "digest", digest(catalog))
    from tripbudget.retrieval import Corpus

    corpus = Corpus(settings)
    await asyncio.to_thread(corpus.build)
    print("Real BGE/Chroma index ready")


if __name__ == "__main__":
    asyncio.run(main())
