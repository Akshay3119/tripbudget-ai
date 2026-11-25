"""Independent audit: no imports from production arithmetic, scheduling, planning or validation."""

import math
from datetime import datetime
from fractions import Fraction


def audit(request, proposal, catalog):
    errors = []

    def require(value, code):
        if not value:
            errors.append(code)

    travelers = {t["id"]: t for t in request["travelers"]}
    n = len(travelers)
    days = request["days"]
    rows = proposal["cost_items"]
    require(len({r["id"] for r in rows}) == len(rows), "duplicate_cost_id")
    amounts = {t: 0 for t in travelers}
    for row in rows:
        require(type(row["unit_cents"]) is int and type(row["quantity"]) is int, "integer_money")
        require(row["total_cents"] == row["unit_cents"] * row["quantity"], "row_multiplication")
        require(set(row["allocations"]) == set(travelers), "allocation_participants")
        require(sum(row["allocations"].values()) == row["total_cents"], "allocation_conservation")
        for t, value in row["allocations"].items():
            require(abs(Fraction(row["total_cents"], n) - value) < 1, "allocation_rounding")
            amounts[t] += value
        if row["category"] == "activity":
            option = next(a for a in catalog["activities"] if a["id"] == row["fact_id"])
            require(row["unit_cents"] == option["price_cents"] and row["quantity"] == n, "catalog_price")
    for d in range(days):
        meals = [r for r in rows if r["day"] == d and r["category"] == "meals"]
        require(
            len(meals) == 1
            and meals[0]["quantity"] == 3 * n
            and meals[0]["unit_cents"] == request.get("meal_cents", 1800),
            "meal_coverage",
        )
        local = [r for r in rows if r["day"] == d and r["category"] == "local_transit"]
        require(
            len(local) == 1 and local[0]["quantity"] == n and local[0]["unit_cents"] == 1500,
            "local_transit_coverage",
        )
    rooms = [r for r in rows if r["category"] == "lodging"]
    require(len(rooms) == days - 1 and {r["day"] for r in rooms} == set(range(days - 1)), "lodging_nights")
    tier = proposal["choice"]["lodging_tier"]
    for room in rooms:
        require(room["quantity"] == math.ceil(n / request.get("room_capacity", 2)), "room_occupancy")
        require(
            room["unit_cents"]
            == request.get("lodging_" + tier + "_cents", 11000 if tier == "economy" else 21000),
            "room_price",
        )
    routes = [r for r in rows if r["category"] == "intercity"]
    require(len(routes) == len(request["cities"]) - 1, "route_coverage")
    for row, (a, b) in zip(routes, zip(request["cities"], request["cities"][1:], strict=False), strict=False):
        route = catalog["routes"]["-".join(sorted([a, b]))]
        require(row["quantity"] == n and row["unit_cents"] == route["price_cents"], "route_price")
    subtotal = sum(r["total_cents"] for r in rows)
    buffer = math.ceil(Fraction(subtotal, 10))
    require(
        proposal["subtotal_cents"] == subtotal
        and proposal["buffer_cents"] == buffer
        and proposal["total_cents"] == subtotal + buffer,
        "full_total",
    )
    require(sum(proposal["traveler_totals"].values()) == subtotal + buffer, "traveler_conservation")
    for t, amount in amounts.items():
        share = proposal["traveler_totals"][t] - amount
        require(abs(Fraction(buffer, n) - share) < 1, "buffer_rounding")
        require(proposal["traveler_totals"][t] <= travelers[t]["budget_cents"], "individual_cap")
    require(
        subtotal + buffer <= request.get("group_budget_cents", None)
        if request.get("group_budget_cents")
        else True,
        "group_cap",
    )
    schedule = proposal["schedule"]
    options = {o["id"]: o for o in catalog["activities"]}
    seen = set()
    for day in range(days):
        entries = sorted([e for e in schedule if e["day"] == day], key=lambda e: e["start"])
        require(any(e["activity_id"] in options for e in entries), "daily_activity_coverage")
        walk = 500
        previous = None
        for e in entries:
            start, end = datetime.fromisoformat(e["start"]), datetime.fromisoformat(e["end"])
            require(start.tzinfo is not None and end > start, "aware_positive_duration")
            require(
                datetime.fromisoformat(e["opening_start"])
                <= start
                < end
                <= datetime.fromisoformat(e["opening_end"]),
                "operating_window",
            )
            if previous:
                require(start >= previous, "no_overlap")
            previous = end
            walk += e["walk_meters"]
            if e["activity_id"] in options:
                o = options[e["activity_id"]]
                seen.add(o["id"])
                require(start.weekday() not in o["closed_weekdays"], "closed_weekday")
                require(start.strftime("%m-%d") not in o.get("closed_dates", []), "closed_date")
                require(int((end - start).total_seconds()) == o["duration_minutes"] * 60, "activity_duration")
                require(e["city"] == o["city"], "activity_city")
        require(walk <= min(t.get("maximum_walk_meters", 12000) for t in travelers.values()), "daily_walking")
    require(set(request.get("required_activities", [])) <= seen, "required_activities")
    return sorted(set(errors))
