"""Frozen case definitions with independent witness construction and named data-gap mutations."""

from .client import default_request


def scenarios():
    cases = []
    definitions = [
        ("F01", 4, 5, ["NYC", "PHL", "DC"], 85000, {}),
        ("F02", 2, 3, ["NYC"], 90000, {}),
        ("F03", 6, 7, ["NYC", "PHL", "DC"], 140000, {}),
        ("F04", 2, 3, ["PHL"], 65000, {}),
        ("F05", 4, 3, ["DC"], 65000, {}),
        ("F06", 3, 5, ["NYC", "PHL", "DC"], 95000, {}),
        ("F07", 4, 5, ["NYC", "PHL", "DC"], 100000, {"unequal": True}),
        ("F08", 4, 5, ["NYC", "PHL", "DC"], 90000, {"walk": 4000}),
        ("F09", 4, 5, ["NYC", "PHL", "DC"], 90000, {"diet": "vegan"}),
        ("F10", 4, 5, ["NYC", "PHL", "DC"], 90000, {"gateway_end_hour": 15}),
        ("F11", 6, 3, ["NYC", "PHL"], 95000, {}),
        ("F12", 4, 5, ["NYC", "PHL", "DC"], 85000, {"group_budget_cents": 310000}),
    ]
    for identifier, count, days, cities, cap, extras in definitions:
        travelers = [
            {
                "id": f"t{i + 1}",
                "budget_cents": (80000 + i * 5000 if extras.get("unequal") else cap),
                "diet": extras.get("diet", "unrestricted"),
                "maximum_walk_meters": extras.get("walk", 12000),
            }
            for i in range(count)
        ]
        request = default_request(
            days=days,
            cities=cities,
            travelers=travelers,
            **{k: v for k, v in extras.items() if k in {"gateway_end_hour", "group_budget_cents"}},
        )
        cases.append(
            {
                "id": identifier,
                "kind": "feasible",
                "request": request,
                "witness": "economy lodging; one free outdoor/history/museum activity per day; manual cost/window oracle",
            }
        )
    for identifier, changes, proof in [
        ("I01", {"cap": 5000}, "Five days of three daily meal allowances alone exceed USD 50/person"),
        ("I02", {"cap": 20000, "days": 7}, "Seven days of meal allowances alone exceed USD 200/person"),
        ("I03", {"group_budget_cents": 10000}, "Mandatory group meals alone exceed USD 100 total"),
        ("I04", {"walk": 500}, "Any catalog activity plus 500m daily transfer allowance exceeds 500m"),
    ]:
        request = default_request()
        if "days" in changes:
            request["days"] = changes["days"]
        if "group_budget_cents" in changes:
            request["group_budget_cents"] = changes["group_budget_cents"]
        for t in request["travelers"]:
            t["budget_cents"] = changes.get("cap", 85000)
            t["maximum_walk_meters"] = changes.get("walk", 12000)
        cases.append({"id": identifier, "kind": "infeasible", "request": request, "proof": proof})
    for identifier, mutation, explanation in [
        ("D01", "missing_fare", "A required route exists but has no numerical fare"),
        ("D02", "expired_activity", "A mandatory candidate source/estimate has expired"),
        ("D03", "missing_route", "No route record supports one requested city transition"),
        ("D04", "unconfirmed_estimate", "The organizer has not confirmed mandatory planning estimates"),
    ]:
        request = default_request()
        if mutation == "unconfirmed_estimate":
            request["estimates_confirmed"] = False
        cases.append(
            {
                "id": identifier,
                "kind": "incomplete",
                "request": request,
                "mutation": mutation,
                "reason": explanation,
            }
        )
    return cases
