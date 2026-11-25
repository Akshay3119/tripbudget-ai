from fractions import Fraction

from .errors import DomainError


def allocate_cents(amount: int, weights: dict[str, int]) -> dict[str, int]:
    if (
        type(amount) is not int
        or amount < 0
        or not weights
        or any(type(w) is not int or w < 0 for w in weights.values())
    ):
        raise ValueError("Nonnegative integer cents/weights required")
    total = sum(weights.values())
    if not total:
        if amount == 0:
            return dict.fromkeys(weights, 0)
        raise ValueError("A nonzero amount requires positive weight")
    exact = {key: Fraction(amount * weight, total) for key, weight in weights.items()}
    result = {key: value.numerator // value.denominator for key, value in exact.items()}
    order = sorted(weights, key=lambda key: (-(exact[key] - result[key]), key))
    for key in order[: amount - sum(result.values())]:
        result[key] += 1
    return result


def summarize(items, traveler_ids):
    base = {identifier: 0 for identifier in traveler_ids}
    for item in items:
        if (
            item.total_cents != item.unit_cents * item.quantity
            or sum(item.allocations.values()) != item.total_cents
        ):
            raise DomainError("ALLOCATION_ERROR", "Item costs must conserve integer cents")
        if set(item.allocations) != set(item.beneficiaries) or not set(item.beneficiaries) <= set(base):
            raise DomainError("ALLOCATION_ERROR", "Item beneficiaries must be known travelers")
        for traveler, value in item.allocations.items():
            if value < 0:
                raise DomainError("ALLOCATION_ERROR", "Negative expense share")
            base[traveler] += value
    subtotal = sum(base.values())
    buffer = (subtotal + 9) // 10
    contingency = allocate_cents(buffer, base)
    totals = {key: base[key] + contingency[key] for key in base}
    return {
        "subtotal_cents": subtotal,
        "buffer_cents": buffer,
        "total_cents": subtotal + buffer,
        "traveler_totals": totals,
        "base_allocations": base,
        "contingency_allocations": contingency,
    }


def financial_violations(request, proposal):
    violations = []
    for traveler in request.travelers:
        actual = proposal["traveler_totals"][traveler.id]
        if actual > traveler.budget_cents:
            violations.append(
                {
                    "code": "OVER_BUDGET",
                    "traveler": traveler.id,
                    "overage_cents": actual - traveler.budget_cents,
                    "actual_cents": actual,
                    "cap_cents": traveler.budget_cents,
                }
            )
    if request.group_budget_cents is not None and proposal["total_cents"] > request.group_budget_cents:
        violations.append(
            {
                "code": "GROUP_OVER_BUDGET",
                "overage_cents": proposal["total_cents"] - request.group_budget_cents,
            }
        )
    return violations


def mandatory_lower_bound(request):
    # A conservative proof uses only mandatory meal spend. It cannot overstate the minimum.
    per_person_meals = request.days * 3 * request.meal_cents
    return per_person_meals + per_person_meals // 10


def infeasibility_reason(request, catalog):
    per_person = mandatory_lower_bound(request)
    if any(t.budget_cents < per_person for t in request.travelers):
        return {"proof": "mandatory meal lower bound", "per_person_lower_bound_cents": per_person}
    group_meals = request.days * 3 * request.meal_cents * len(request.travelers)
    group_min = group_meals + (group_meals + 9) // 10
    if request.group_budget_cents is not None and request.group_budget_cents < group_min:
        return {"proof": "mandatory group meals and contingency", "group_lower_bound_cents": group_min}
    for city in request.cities:
        options = [o for o in catalog.activities.values() if o["city"] == city]
        if options:
            walk_min = min(o["walk_meters"] for o in options) + 500
            if any(t.maximum_walk_meters < walk_min for t in request.travelers):
                return {
                    "proof": "at least one daily activity plus minimum transfer walking",
                    "city": city,
                    "daily_walk_lower_bound_meters": walk_min,
                }
    return None
