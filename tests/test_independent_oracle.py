"""A second implementation audits production outputs and catches deliberate mutations."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from evaluation.oracle import audit
from evaluation.scenarios import scenarios
from tripbudget.planning import build_proposal, enumerate_repairs
from tripbudget.schemas import PlanChoice, TripRequest


@pytest.mark.parametrize("case", scenarios()[:12], ids=lambda x: x["id"])
def test_every_feasible_scenario_has_independently_audited_witness(catalog, case):
    req = TripRequest.model_validate(case["request"])
    candidates = enumerate_repairs(req, catalog)
    assert candidates
    proposal = build_proposal(req, PlanChoice.model_validate(candidates[0]["choice"]), catalog)
    assert audit(case["request"], proposal, catalog.data) == []


@pytest.mark.parametrize("category", ["meals", "lodging", "local_transit", "intercity"])
def test_independent_oracle_detects_missing_mandatory_cost(catalog, category):
    case = scenarios()[0]
    req = TripRequest.model_validate(case["request"])
    choice = PlanChoice.model_validate(enumerate_repairs(req, catalog)[0]["choice"])
    proposal = deepcopy(build_proposal(req, choice, catalog))
    index = next(i for i, r in enumerate(proposal["cost_items"]) if r["category"] == category)
    proposal["cost_items"].pop(index)
    assert audit(case["request"], proposal, catalog.data)


@pytest.mark.parametrize("count", [2, 3, 4, 5, 6])
def test_odd_group_room_capacity_and_cent_conservation(catalog, count):
    case = scenarios()[0]
    case["request"]["travelers"] = [{"id": f"t{i + 1}", "budget_cents": 150000} for i in range(count)]
    req = TripRequest.model_validate(case["request"])
    p = build_proposal(req, PlanChoice.model_validate(enumerate_repairs(req, catalog)[0]["choice"]), catalog)
    assert all(r["quantity"] == (count + 1) // 2 for r in p["cost_items"] if r["category"] == "lodging")
    assert audit(case["request"], p, catalog.data) == []


def test_source_manifest_detects_tampering(tmp_path):
    from tripbudget.evidence import Catalog
    from tripbudget.errors import DomainError

    source = Path("corpus/catalog.json")
    data = json.loads(source.read_text())
    data["activities"][0]["price_cents"] = 1
    (tmp_path / "catalog.json").write_text(json.dumps(data))
    (tmp_path / "manifest.json").write_text(Path("corpus/manifest.json").read_text())
    with pytest.raises(DomainError):
        Catalog(tmp_path / "catalog.json")
