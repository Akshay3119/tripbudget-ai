import hashlib
import json
from datetime import datetime

from .errors import DomainError
from .settings import ROOT


class Catalog:
    def __init__(self, path=None):
        self.path = path or ROOT / "corpus" / "catalog.json"
        self.reload()

    def reload(self):
        raw = self.path.read_bytes()
        manifest = json.loads((self.path.parent / "manifest.json").read_text())
        if hashlib.sha256(raw).hexdigest() != manifest["catalog_sha256"]:
            raise DomainError("CATALOG_INTEGRITY", "Catalog does not match release manifest", 503)
        self.data = json.loads(raw)
        self.version = self.data["version"]
        self.sha256 = manifest["catalog_sha256"]
        self.activities = {x["id"]: x for x in self.data["activities"]}
        self.sources = {x["source_id"]: x for x in self.data["sources"]}

    def option(self, identifier, now):
        option = self.activities.get(identifier)
        if not option:
            raise DomainError("DATA_GAP", "Unknown activity option: " + identifier)
        if datetime.fromisoformat(option["expires_at"]) <= now:
            raise DomainError("DATA_GAP", "Activity source/estimate has expired: " + identifier)
        if option["evidence_state"] not in {"VERIFIED_SNAPSHOT", "USER_ESTIMATE"}:
            raise DomainError("DATA_GAP", "Activity has no eligible planning price")
        if option["evidence_state"] == "VERIFIED_SNAPSHOT":
            source = self.sources[option["source_id"]]
            if (
                source["fetch_status"] != "OK"
                or "price_cents" not in option["reviewed_fields"]
                or option.get("review_source_sha256") != source["sha256"]
            ):
                raise DomainError("DATA_GAP", "Numerical source has not been independently reviewed")
        return option

    def validate_price(self, identifier, amount_cents, evidence_state, now):
        option = self.option(identifier, now)
        if amount_cents != option["price_cents"] or evidence_state != option["evidence_state"]:
            raise DomainError("SOURCE_MISMATCH", "Claimed amount or evidence class differs from catalog")
        return option

    def compact(self, cities, now):
        result = []
        for option in self.activities.values():
            if option["city"] in cities:
                self.option(option["id"], now)
                result.append(
                    {
                        k: option[k]
                        for k in [
                            "id",
                            "city",
                            "title",
                            "category",
                            "price_cents",
                            "duration_minutes",
                            "walk_meters",
                            "closed_weekdays",
                        ]
                    }
                )
        return result

    def route(self, origin, destination, now):
        key = "-".join(sorted([origin, destination]))
        route = self.data.get("routes", {}).get(key)
        if (
            not route
            or type(route.get("price_cents")) is not int
            or route["price_cents"] < 0
            or type(route.get("duration_minutes")) is not int
            or route["duration_minutes"] <= 0
            or datetime.fromisoformat(route["expires_at"]) <= now
        ):
            raise DomainError("DATA_GAP", "Intercity route/fare/duration is missing or expired: " + key)
        return route
