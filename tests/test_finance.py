import random
from copy import deepcopy

import pytest
from pydantic import ValidationError

from evaluation.client import default_request
from tripbudget.budget import allocate_cents
from tripbudget.errors import DomainError
from tripbudget.planning import build_proposal, validate_for_commit
from tripbudget.schemas import PlanChoice, TripRequest


@pytest.mark.parametrize("count", range(2, 7))
def test_allocation_conserves_odd_cents_and_weight_ratios(count):
    rng = random.Random(599 + count)
    for _ in range(100):
        amount = rng.randint(0, 1_000_000)
        weights = {f"t{i}": rng.randint(1, 9) for i in range(count)}
        allocation = allocate_cents(amount, weights)
        assert sum(allocation.values()) == amount
        assert all(v >= 0 for v in allocation.values())
        assert all(abs(allocation[k] - amount * w / sum(weights.values())) < 1 for k, w in weights.items())


@pytest.mark.parametrize("bad", [-1, 0.1, True, "12"])
def test_allocation_rejects_noninteger_or_negative_amount(bad):
    with pytest.raises(ValueError):
        allocate_cents(bad, {"t1": 1, "t2": 1})


@pytest.mark.parametrize("bad", [-100, 4999, 1000001, 50000.5, True])
def test_request_cannot_smuggle_invalid_budget(bad):
    data = default_request()
    data["travelers"][0]["budget_cents"] = bad
    with pytest.raises(ValidationError):
        TripRequest.model_validate(data)


def choice_for(catalog, cities):
    return PlanChoice(
        lodging_tier="economy",
        activities_per_day=1,
        activities={c: [o["id"] for o in catalog.activities.values() if o["city"] == c] for c in cities},
        explanation="Test fixture",
    )


def test_real_catalog_assembly_accounts_every_day_night_and_person(catalog):
    request = TripRequest.model_validate(default_request())
    p = build_proposal(request, choice_for(catalog, request.cities), catalog)
    assert sum(p["traveler_totals"].values()) == p["total_cents"]
    assert p["buffer_cents"] == (p["subtotal_cents"] + 9) // 10
    costs = p["cost_items"]
    assert len([x for x in costs if x["category"] == "lodging"]) == request.days - 1
    assert sum(x["quantity"] for x in costs if x["category"] == "meals") == 3 * request.days * len(
        request.travelers
    )
    assert sum(x["total_cents"] for x in costs if x["category"] == "lodging") == 4 * 2 * 11000
    assert len([x for x in costs if x["category"] == "intercity"]) == 2


def test_unequal_individual_cap_fails_even_when_group_cap_fits(catalog):
    data = default_request()
    data["travelers"][0]["budget_cents"] = 5000
    data["group_budget_cents"] = 1_000_000
    request = TripRequest.model_validate(data)
    p = build_proposal(request, choice_for(catalog, request.cities), catalog)
    assert any(v["code"] == "OVER_BUDGET" and v["traveler"] == "t1" for v in p["violations"])


def test_recomputed_commit_detects_removed_cost(catalog):
    request = TripRequest.model_validate(default_request())
    p = build_proposal(request, choice_for(catalog, request.cities), catalog)
    changed = deepcopy(p)
    changed["cost_items"].pop(0)
    with pytest.raises(DomainError):
        validate_for_commit(changed, request.model_dump(mode="json"), catalog)


def test_model_cannot_invent_valid_activity_id(catalog):
    request = TripRequest.model_validate(default_request())
    choice = choice_for(catalog, request.cities)
    choice.activities["NYC"] = ["invented-free-penthouse"]
    with pytest.raises(DomainError, match="Unknown activity"):
        build_proposal(request, choice, catalog)
