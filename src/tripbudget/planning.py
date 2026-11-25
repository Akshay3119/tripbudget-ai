import math
from datetime import timedelta

from .budget import allocate_cents, financial_violations, summarize
from .errors import DomainError
from .persistence import digest
from .schedule import city_days, local_time, schedule_violations, scheduled_activity
from .schemas import CostItem, PlanChoice, ScheduledItem, TripRequest, utcnow


def build_proposal(request: TripRequest, choice: PlanChoice, catalog, revision=1, now=None):
    now = now or utcnow()
    ids = [t.id for t in request.travelers]
    n = len(ids)
    items, schedule, violations, facts_read = [], [], [], []
    assignments = city_days(request)

    def add(
        identifier, category, day, city, description, unit, quantity, evidence="USER_ESTIMATE", fact_id=None
    ):
        amount = unit * quantity
        items.append(
            CostItem(
                id=identifier,
                category=category,
                day=day,
                city=city,
                description=description,
                unit_cents=unit,
                quantity=quantity,
                total_cents=amount,
                beneficiaries=ids,
                allocations=allocate_cents(amount, dict.fromkeys(ids, 1)),
                evidence_state=evidence,
                fact_id=fact_id,
                estimate_id=None if fact_id else identifier,
            )
        )

    pools = {}
    for city in request.cities:
        selected = choice.activities.get(city, [])
        for identifier in selected:
            option = catalog.option(identifier, now)
            if option["city"] != city:
                raise DomainError("INVALID_OPTION", "Selected activity is in another city")
        pools[city] = list(dict.fromkeys(selected))
    for identifier in request.required_activities:
        option = catalog.option(identifier, now)
        if option["city"] not in pools:
            raise DomainError("DATA_GAP", "Required activity is outside requested cities")
        if identifier not in pools[option["city"]]:
            pools[option["city"]].insert(0, identifier)
    visited = []
    for day, city in enumerate(assignments):
        date = request.start_date + timedelta(days=day)
        add(
            f"meals-{day}",
            "meals",
            day,
            city,
            "Three all-in meal allowances per traveler",
            request.meal_cents,
            3 * n,
        )
        add(
            f"local-{day}",
            "local_transit",
            day,
            city,
            "Local transit/transfer planning allowance, taxes/fees included",
            1500,
            n,
        )
        if day < request.days - 1:
            room_price = (
                request.lodging_economy_cents
                if choice.lodging_tier == "economy"
                else request.lodging_standard_cents
            )
            add(
                f"lodging-{day}",
                "lodging",
                day,
                city,
                f"{choice.lodging_tier.title()} lodging, all-in per room/night, capacity {request.room_capacity}",
                room_price,
                math.ceil(n / request.room_capacity),
            )
        cursor = local_time(date, 10)
        if day and city != assignments[day - 1]:
            route = catalog.route(assignments[day - 1], city, now)
            cost, duration = route["price_cents"], route["duration_minutes"]
            departure = local_time(date, 8, 30)
            arrival = departure + timedelta(minutes=duration)
            schedule.append(
                ScheduledItem(
                    id=f"intercity-{day}",
                    activity_id=f"route-{assignments[day - 1]}-{city}",
                    day=day,
                    city=city,
                    start=departure,
                    end=arrival,
                    opening_start=local_time(date, 8),
                    opening_end=local_time(date, 18),
                    transfer_minutes=0,
                    buffer_minutes=0,
                    walk_meters=500,
                    evidence_state="USER_ESTIMATE",
                )
            )
            add(
                f"intercity-{day}",
                "intercity",
                day,
                city,
                "Intercity all-in fare estimate; no seat reservation",
                cost,
                n,
            )
            cursor = max(cursor, arrival + timedelta(minutes=45))
        available = []
        for identifier in pools[city]:
            option = catalog.option(identifier, now)
            closed = date.weekday() in option["closed_weekdays"] or date.strftime("%m-%d") in option.get(
                "closed_dates", []
            )
            if closed:
                continue
            if identifier not in visited:
                available.append(option)
        # One or two activities per day. Revisit an outdoor option only when a long single-city stay exhausts IDs.
        if not available:
            available = [
                catalog.option(x, now) for x in pools[city] if catalog.activities[x]["category"] == "park"
            ][:1]
        for option in available[: choice.activities_per_day]:
            start = max(cursor, local_time(date, option["open_hour"]))
            item = scheduled_activity(option, day, date, start)
            if item.end > item.opening_end:
                continue
            schedule.append(item)
            visited.append(option["id"])
            facts_read.append(
                {
                    "id": option["id"],
                    "source_id": option["source_id"],
                    "price_cents": option["price_cents"],
                    "evidence_state": option["evidence_state"],
                }
            )
            add(
                f"ticket-{day}-{option['id']}",
                "activity",
                day,
                city,
                option["title"],
                option["price_cents"],
                n,
                option["evidence_state"],
                option["id"],
            )
            cursor = item.end + timedelta(minutes=45)
        if not any(x.day == day and not x.activity_id.startswith("route-") for x in schedule):
            violations.append({"code": "NO_ACTIVITY_COVERAGE", "day": day, "city": city})
    for required in request.required_activities:
        if required not in visited:
            violations.append({"code": "REQUIRED_ACTIVITY_MISSING", "activity": required})
    totals = summarize(items, ids)
    violations += financial_violations(request, totals)
    violations += schedule_violations(request, schedule)
    proposal = {
        "revision": revision,
        "constraints_hash": digest(request.model_dump(mode="json")),
        "corpus_version": catalog.version,
        "evidence_digest": catalog.sha256,
        "choice": choice.model_dump(),
        "cost_items": [x.model_dump(mode="json") for x in items],
        "schedule": [x.model_dump(mode="json") for x in schedule],
        **totals,
        "violations": violations,
        "valid": not violations,
        "facts_read": facts_read,
        "scope": "City gateway to gateway. Flights/home travel excluded. Planning ledger; no bookings.",
        "assumptions": [
            "All lodging, meals, local/intercity transit and route durations are confirmed planning estimates.",
            "Activity windows and walking distances are planning assumptions; no real-time availability.",
            "Three meals daily, room capacity enforced, 10% contingency, USD integer cents.",
        ],
    }
    return proposal


def validate_for_commit(proposal, raw_request, catalog):
    request = TripRequest.model_validate(raw_request)
    choice = PlanChoice.model_validate(proposal["choice"])
    rebuilt = build_proposal(request, choice, catalog, revision=proposal["revision"])
    if not rebuilt["valid"]:
        raise DomainError("INVALID_PLAN", "The proposal no longer satisfies every hard constraint", 409)
    if digest(rebuilt) != digest(proposal):
        raise DomainError("PLAN_CHANGED", "Recomputed amounts/evidence differ from approved proposal", 409)
    return rebuilt


def enumerate_repairs(request, catalog):
    """Bounded read-only tool: compute feasible alternatives without trusting LLM arithmetic."""
    candidates = []
    for tier in ["economy", "standard"]:
        for cadence in [1, 2]:
            for free_only in [True, False]:
                activities = {
                    city: [
                        o["id"]
                        for o in catalog.activities.values()
                        if o["city"] == city and (not free_only or o["price_cents"] == 0)
                    ]
                    for city in request.cities
                }
                choice = PlanChoice(
                    lodging_tier=tier,
                    activities_per_day=cadence,
                    activities=activities,
                    explanation="Tool-priced alternative satisfying the declared constraints",
                )
                proposal = build_proposal(request, choice, catalog)
                if proposal["valid"]:
                    choice.expected_cost_cents = proposal["total_cents"]
                    visited = {x["activity_id"] for x in proposal["schedule"]}
                    rank = (
                        -len(visited & set(request.wishlist)),
                        proposal["total_cents"],
                        sum(x["walk_meters"] for x in proposal["schedule"]),
                    )
                    candidates.append(
                        (
                            rank,
                            {
                                "choice": choice.model_dump(),
                                "valid": True,
                                "total_cents": proposal["total_cents"],
                                "traveler_totals": proposal["traveler_totals"],
                            },
                        )
                    )
    return [x[1] for x in sorted(candidates, key=lambda x: x[0])][:3]
