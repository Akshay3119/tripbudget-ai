import json
from pathlib import Path
from evaluation.oracle import audit
from evaluation.scenarios import scenarios
from tripbudget.evidence import Catalog
from tripbudget.planning import build_proposal, enumerate_repairs
from tripbudget.schemas import PlanChoice, TripRequest

catalog = Catalog(Path("corpus/catalog.json"))
results = []
for case in scenarios()[:12]:
    request = TripRequest.model_validate(case["request"])
    choice = PlanChoice.model_validate(enumerate_repairs(request, catalog)[0]["choice"])
    proposal = build_proposal(request, choice, catalog)
    errors = audit(case["request"], proposal, catalog.data)
    results.append(
        {
            "case": case["id"],
            "independent_audit_errors": errors,
            "request": case["request"],
            "witness": proposal,
            "origin": "bounded production search; audited by separate Fraction-based accounting/window oracle, not human review",
        }
    )
Path("evaluation/witnesses.json").write_text(json.dumps(results, indent=2))
print({r["case"]: r["independent_audit_errors"] for r in results})
assert not any(r["independent_audit_errors"] for r in results)
