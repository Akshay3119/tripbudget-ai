"""Resolve source ranges from the packaged source, never placeholder line numbers."""

import ast
import json
from pathlib import Path

ROWS = [
    (
        "Advanced Feature 1",
        "Long-term confirmed preference memory",
        [
            ("src/tripbudget/persistence.py", "Store.save_preferences"),
            ("src/tripbudget/graph.py", "Workflow.build_graph.load"),
        ],
        "Versioned owner/group scope; explicit confirmation; actual process replacement in video",
    ),
    (
        "Advanced Feature 2",
        "Planning and self-correction",
        [
            ("src/tripbudget/graph.py", "Workflow.build_graph.supervisor"),
            ("src/tripbudget/graph.py", "Workflow.build_graph.assemble"),
            ("src/tripbudget/planning.py", "enumerate_repairs"),
            ("src/tripbudget/schemas.py", "plan_choice_schema"),
        ],
        "Real model choice → deterministic critique → indexed tool-priced repair → recheck; at most two repairs",
    ),
    (
        "Advanced Feature 3",
        "Durable human-in-the-loop approval",
        [
            ("src/tripbudget/graph.py", "Workflow.build_graph.approval"),
            ("src/tripbudget/persistence.py", "Store.record_decision"),
            ("src/tripbudget/persistence.py", "Store.commit_approved"),
        ],
        "Official interrupt/checkpoint; owner/hash/revision/expiry; one authorized ledger",
    ),
    (
        "Advanced Feature 4",
        "Iterative RAG and source verification",
        [
            ("src/tripbudget/retrieval.py", "Corpus.retrieve_and_refine"),
            ("src/tripbudget/evidence.py", "Catalog.option"),
        ],
        "Actual BGE/Chroma refinement; reviewed price snapshots separate from confirmed estimates",
    ),
    (
        "Advanced Feature 5",
        "Hybrid cloud/local inference",
        [
            ("src/tripbudget/routing.py", "select_route"),
            ("src/tripbudget/providers.py", "Providers.complete"),
        ],
        "Real NVIDIA + E4B local demo; private input cannot fall back externally; no cloud laptop bridge claimed",
    ),
    (
        "Guardrail 1",
        "Accounting, schedule and immutable evidence",
        [
            ("src/tripbudget/budget.py", "financial_violations"),
            ("src/tripbudget/planning.py", "validate_for_commit"),
            ("src/tripbudget/schedule.py", "schedule_violations"),
        ],
        "Every cap/night/meal/room/transfer; integer cents; commit revalidation",
    ),
    (
        "Guardrail 2",
        "Owner and tool/egress permissions",
        [
            ("src/tripbudget/auth.py", "principal"),
            ("src/tripbudget/outbound.py", "validate_url"),
            ("src/tripbudget/tools.py", "authorize_tool"),
        ],
        "Read-only capabilities; registered public HTTPS; owner predicates; no mail/shell/booking authority",
    ),
    (
        "Guardrail 3",
        "Persisted budgets and worker ownership",
        [
            ("src/tripbudget/resources.py", "Budget.reserve"),
            ("src/tripbudget/persistence.py", "Store.invocation"),
        ],
        "Session-bound advisory lock; call/token/time quotas and conservative unknown usage",
    ),
    (
        "Guardrail 4",
        "Native output contract, complete candidate pools and supported local backend",
        [
            ("src/tripbudget/providers.py", "validate_output"),
            ("src/tripbudget/providers.py", "Providers.check_local_backend"),
            ("src/tripbudget/schemas.py", "plan_choice_schema"),
        ],
        "GGUF preflight; no silent defaults/truncated JSON; full client uniqueness validation despite native grammar projection",
    ),
    (
        "Adversarial Evals",
        "Ten actual attack types, twice",
        [("evaluation/run_attacks.py", "main")],
        "20 attempts; exact model exposure, full real traces and mitigations in report",
    ),
    (
        "Evaluation Harness",
        "Custom paired tasks, metrics and independent audit",
        [
            ("evaluation/run_eval.py", "execute"),
            ("evaluation/oracle.py", "audit"),
            ("evaluation/build_report.py", "main"),
            ("evaluation/build_followup_report.py", "main"),
        ],
        "154 historical units + 151 fresh release units; real providers/outage/operations; fixtures separate; measured tokens/session",
    ),
    (
        "Deployment / Persistence",
        "Cloud Run service alternative + external PostgreSQL",
        [
            ("src/tripbudget/persistence.py", "Store.migrate"),
            ("src/tripbudget/graph.py", "Workflow.build_graph"),
        ],
        "Official AsyncPostgresSaver; historical IAM-private cloud smoke and current local container check; see handoff for rollout status",
    ),
]


def symbols(path):
    found = {}

    def walk(node, prefix=""):
        for n in ast.iter_child_nodes(node):
            if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                qualified = prefix + n.name
                found[qualified] = (n.lineno, n.end_lineno)
                walk(n, qualified + ".")
            else:
                walk(n, prefix)

    walk(ast.parse(Path(path).read_text()))
    return found


def main():
    records = []
    table = [
        "## Capability-to-Code Map",
        "",
        "| Category | Claimed Feature / Guardrail / Eval | Source File(s) & Line Numbers | Key Class / Function | Notes / Scope |",
        "|---|---|---|---|---|",
    ]
    for category, claim, refs, notes in ROWS:
        resolved = []
        for path, symbol in refs:
            start, end = symbols(path)[symbol]
            resolved.append({"path": path, "symbol": symbol, "start": start, "end": end})
        files = "<br>".join(
            f"[{r['path']} L{r['start']}–L{r['end']}]({r['path']}#L{r['start']}-L{r['end']})"
            for r in resolved
        )
        keys = "<br>".join("`" + r["symbol"] + "`" for r in resolved)
        table.append(f"| {category} | {claim} | {files} | {keys} | {notes} |")
        records.append({"category": category, "claim": claim, "references": resolved, "notes": notes})
    table += [
        "",
        "Deployment configuration: [Dockerfile](Dockerfile), [Cloud Run spec](infra/cloudrun.yaml), [operations and runtime modes](infra/README.md). All five claimed capabilities are tied to actual video segments and raw trace IDs in [recording evidence](docs/recording-evidence.md). Source and artifact SHA-256 inventories are in the release manifest.",
    ]
    p = Path("README.md")
    s = p.read_text()
    start = s.index("<!-- CAPABILITY_MAP -->") + len("<!-- CAPABILITY_MAP -->")
    end = s.find("<!-- END_CAPABILITY_MAP -->", start)
    if end < 0:
        end = start
    s = s[:start] + "\n\n" + "\n".join(table) + "\n\n" + s[end:]
    if "<!-- END_CAPABILITY_MAP -->" not in s:
        s = s[:start] + s[start:].replace(
            "\n\n## Attribution", "\n\n<!-- END_CAPABILITY_MAP -->\n\n## Attribution", 1
        )
    p.write_text(s)
    Path("docs/capability-map.json").write_text(json.dumps(records, indent=2))
    print("Resolved", len(records), "capability/guardrail/evaluation/deployment rows.")


if __name__ == "__main__":
    main()
