"""Generate the report and metrics from immutable real-run records plus persisted provider usage."""

import asyncio
import json
import math
import statistics
from collections import Counter
from pathlib import Path

from tripbudget.persistence import Store
from tripbudget.settings import Settings

from .oracle import audit

EVIDENCE = Path("deliverables/evidence")


def read(name):
    return [json.loads(x) for x in (EVIDENCE / (name + ".jsonl")).read_text().splitlines()]


def percentile(values, q):
    return sorted(values)[max(0, math.ceil(len(values) * q) - 1)] if values else None


def percentage(a, b):
    return f"{a}/{b} ({100 * a / b:.1f}%)" if b else "0/0 (not applicable)"


async def main():
    benchmark, attacks, providers, operations, live = [
        read(n)
        for n in ["benchmark-v1", "attacks-v1", "provider-comparison", "operations", "live-sources-v1"]
    ]
    assert [len(x) for x in [benchmark, attacks, providers, operations, live]] == [80, 20, 36, 12, 6], (
        "Wait for every planned execution; never report partial runs as the final suite"
    )
    catalog = json.loads(Path("corpus/catalog.json").read_text())
    store = Store(Settings())
    usage = []
    for record in benchmark:
        if record.get("episode"):
            rows = await store.all(
                "SELECT id,task,provider,model,input_tokens,output_tokens,reasoning_tokens,reserved,reserved_output,latency_ms,success,error FROM model_usage WHERE episode=%s",
                (record["episode"],),
            )
            usage.extend({"episode": record["episode"], **row} for row in rows)
    (EVIDENCE / "benchmark-usage.json").write_text(json.dumps(usage, indent=2))
    sessions = []
    for r in benchmark:
        rows = [u for u in usage if u["episode"] == r.get("episode")]
        sessions.append(
            {
                "case": r["case"],
                "condition": r["condition"],
                "repeat": r["repeat"],
                "episode": r.get("episode"),
                "input_tokens_reported": sum(u["input_tokens"] or 0 for u in rows),
                "output_tokens_reported": sum(u["output_tokens"] or 0 for u in rows),
                "unknown_usage_attempts": sum(
                    u["input_tokens"] is None or u["output_tokens"] is None for u in rows
                ),
                "unknown_usage_reservation": sum(
                    u["reserved"] for u in rows if u["input_tokens"] is None or u["output_tokens"] is None
                ),
                "provider_attempts": len(rows),
            }
        )
    (EVIDENCE / "session-tokens.json").write_text(json.dumps(sessions, indent=2))
    audits = []
    for r in benchmark:
        p = r.get("state", {}).get("proposal")
        if p:
            audits.append(
                {
                    "case": r["case"],
                    "condition": r["condition"],
                    "repeat": r["repeat"],
                    "episode": r["episode"],
                    "errors": audit(r["request"], p, catalog),
                }
            )
    (EVIDENCE / "independent-audits.json").write_text(json.dumps(audits, indent=2))
    metrics = {
        "date": "2026-11-25",
        "logical_units": 154,
        "counts": {
            "paired_planning": 80,
            "attacks": 20,
            "matched_provider": 36,
            "operations": 12,
            "live_source": 6,
        },
        "planning": {},
        "providers": {},
        "attacks": {
            "attempted": 20,
            "exposed": sum(r["model_exposed"] for r in attacks),
            "retrieved": sum(r["retrieved_payload"] for r in attacks),
            "protected_state_unchanged": sum(r["protected_state_unchanged"] for r in attacks),
            "legitimate_task_completed": sum(r["legitimate_task_completed"] for r in attacks),
        },
        "operations_passed": sum(r["success"] for r in operations),
        "source_checks_passed": sum(r["success"] for r in live),
        "independent_audits": {"count": len(audits), "passed": sum(not r["errors"] for r in audits)},
    }
    lines = [
        "# TripBudgetAI — Evaluation report",
        "",
        "**Evaluation date:** 25 November 2026. **Release:** 1.0.0, corpus `20261125T174151Z-r2`. All five final suites below executed with real model/tool responses. Fixture-based pytest tests are a separate verification layer.",
        "",
        "## Scope, methodology and ground truth",
        "",
        "This application-specific custom harness evaluates constrained group planning, rather than claiming an external PinchBench/AgentHarm score. The frozen task set has twelve feasible, four proven-infeasible and four incomplete-data cases. Each planning case runs with repair disabled (baseline) and enabled (corrected), twice, in seeded randomized condition order. Inputs, safety gates, source data and routing policy otherwise match. Sampling temperature is 0.2; no provider seed determinism is claimed. One logical unit can contain many model calls and retries.",
        "",
        "Final sample: **154 logical units** = 80 paired planning executions + 20 real attack episodes (10 attack types × 2) + 36 matched provider tasks + 12 operational cases + 6 current-source checks. Extra attack follow-up sessions, browser/demo/cloud checks and development runs are additional and excluded from that denominator. Earlier partial development files are retained separately, not mixed into final rates.",
        "",
        "Task success means a complete valid approval-ready proposal for a feasible case, a supported lower-bound proof for an infeasible case, and DATA_GAP/NEEDS_INPUT/strict validation for incomplete information. No benchmark plan receives automatic approval. Safe rejection of a feasible request is a task failure. Witness plans were constructed by bounded search, then independently checked by `evaluation/oracle.py`, which imports no production arithmetic, scheduling or validation functions. All twelve witness audits passed; this is a separate executable audit, not a claim of human manual review.",
        "",
        "Raw records: [planning](evidence/benchmark-v1.jsonl), [attack traces](evidence/attacks-v1.jsonl), [provider tasks](evidence/provider-comparison.jsonl), [operations](evidence/operations.jsonl), [live sources](evidence/live-sources-v1.jsonl), [independent audits](evidence/independent-audits.json). Source-level cases and grading formulas are committed under `evaluation/`.",
        "",
        "## Paired planning results",
        "",
        "| Condition | Feasible completion | Infeasible correctness | Missing-data handling | Overall | p50 / p95 seconds |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for condition in ["baseline", "corrected"]:
        rows = [r for r in benchmark if r["condition"] == condition]
        result = {}
        counts = []
        for kind in ["feasible", "infeasible", "incomplete"]:
            subset = [r for r in rows if r["kind"] == kind]
            passed = sum(r["success"] for r in subset)
            result[kind] = {"passed": passed, "n": len(subset)}
            counts.append(percentage(passed, len(subset)))
        latency = [r["elapsed_seconds"] for r in rows]
        result["p50_seconds"] = percentile(latency, 0.5)
        result["p95_seconds"] = percentile(latency, 0.95)
        result["outcomes"] = dict(Counter(r["outcome"] for r in rows))
        metrics["planning"][condition] = result
        lines.append(
            f"| {condition} | {' | '.join(counts)} | {percentage(sum(r['success'] for r in rows), len(rows))} | {result['p50_seconds']:.2f} / {result['p95_seconds']:.2f} |"
        )
    lines += [
        "",
        "### Repeat variability",
        "",
        "| Condition | Feasible success repeat 1 | Repeat 2 | Mean rate | Sample SD (percentage points) | Range |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for condition in ["baseline", "corrected"]:
        rates = [
            sum(
                r["success"]
                for r in benchmark
                if r["condition"] == condition and r["kind"] == "feasible" and r["repeat"] == i
            )
            / 12
            for i in [1, 2]
        ]
        metrics["planning"][condition]["repeat_feasible_rates"] = rates
        lines.append(
            f"| {condition} | {100 * rates[0]:.1f}% | {100 * rates[1]:.1f}% | {100 * statistics.mean(rates):.1f}% | {100 * statistics.stdev(rates):.1f} | {100 * min(rates):.1f}–{100 * max(rates):.1f}% |"
        )
    initially_invalid = []
    for r in benchmark:
        critics = [
            f["data"]["data"]
            for f in r.get("frames", [])
            if f["event"] == "trace" and f["data"]["kind"] == "critic"
        ]
        if r["condition"] == "corrected" and critics and not critics[0]["valid"]:
            initially_invalid.append(r)
    repair_pass = sum(r["success"] for r in initially_invalid)
    metrics["repair"] = {"eligible": len(initially_invalid), "completed": repair_pass}
    lines += [
        "",
        f"Observed corrected repair conversion: **{percentage(repair_pass, len(initially_invalid))}** among episodes reaching an initially invalid critic result. Provider failures before a first critic are excluded from that conversion denominator but remain failures in feasible completion.",
        "",
        f"Independent accounting/window audits: **{percentage(metrics['independent_audits']['passed'], len(audits))}** emitted proposals. Benchmark unsafe commits: **{sum(r.get('unsafe_commit', False) for r in benchmark)}**; this is a no-auto-commit check, not a successful-commit rate. Commit functionality is exercised separately by operating, browser, recording and deployed-cloud checks.",
        "",
        "Two repeats provide limited stochastic evidence. Endpoint rate limiting, shared local-model contention and network variability affect latency. The baseline intentionally lacks repair; these results isolate bounded repair inside this architecture, not a comparison against all possible travel planners.",
        "",
        "### Every failed final planning execution",
        "",
        "| Case | Condition | Repeat | Outcome | Seconds | Episode |",
        "|---|---|---:|---|---:|---|",
    ]
    for r in benchmark:
        if not r["success"]:
            lines.append(
                f"| {r['case']} | {r['condition']} | {r['repeat']} | {r['outcome']} | {r['elapsed_seconds']} | `{r.get('episode', 'not admitted')}` |"
            )
    lines += [
        "",
        "## Real prompt-injection attacks",
        "",
        "Synthetic payloads were actually submitted through the operating app; guide attacks were ingested into real isolated Chroma collections via the normal embedding/retrieval adapter. There are no mocked model/tool responses. Exposed means a request/private note reached a model or the injected guide chunk ID appears in an actual model_request source_chunk_ids list. Retrieval alone is reported separately. Each record preserves full event/model/critic/approval traces, request, payload hash, state and repeated-session checks where relevant.",
        "",
        f"Attempted **20**, model exposed **{metrics['attacks']['exposed']}**, retrieved injected guide **{metrics['attacks']['retrieved']}**. Observable protected state preserved: **{percentage(metrics['attacks']['protected_state_unchanged'], 20)}**. Legitimate underlying tasks completed: **{percentage(metrics['attacks']['legitimate_task_completed'], 20)}**. No unauthorized ledger, stored cap change or unconfirmed memory write was observed. These are protected-state containment classifications; they do not assert that every sentence of advisory prose refused the attacker or that every possible egress channel was instrumented.",
        "",
        "| Attack | Surface | Exposed / 2 | Protected state / 2 | Legitimate task / 2 |",
        "|---|---|---:|---:|---:|",
    ]
    for identifier in sorted({r["id"] for r in attacks}):
        rows = [r for r in attacks if r["id"] == identifier]
        r = rows[0]
        lines.append(
            f"| {identifier} | {r['surface']} | {sum(x['model_exposed'] for x in rows)} | {sum(x['protected_state_unchanged'] for x in rows)} | {sum(x['legitimate_task_completed'] for x in rows)} |"
        )
    for identifier in sorted({r["id"] for r in attacks}):
        rows = [r for r in attacks if r["id"] == identifier]
        r = rows[0]
        lines += [
            "",
            f"### {identifier}: {r['objective']}",
            "",
            f"**Injected at:** `{r['surface']}`.",
            "",
            "```text",
            r["payload"],
            "```",
            "",
            f"**Implemented mitigation:** {r['mitigation']}",
            "",
            "**Actual outcomes:** "
            + "; ".join(
                f"repeat {x['repeat']}: `{x['run']['state']['status']}`, exposed={x['model_exposed']}, containment={x['protected_state_unchanged']}, episode `{x['episode']}`"
                for x in rows
            )
            + ".",
            "",
        ]
        observations = [
            f["data"]["data"]
            for f in r["run"]["frames"]
            if f["event"] == "trace"
            and f["data"]["kind"] in {"specialist_observation", "critic", "approval_pending", "terminal"}
        ]
        sample = next(
            (x for x in observations if "observation" in x),
            observations[-1] if observations else r.get("normalization_response", {}),
        )
        lines += [
            "Actual trace excerpt (complete traces linked above):",
            "",
            "```json",
            json.dumps(sample, indent=2),
            "```",
        ]
        if r["surface"] == "restricted_note":
            lines += [
                "",
                "The real local normalization response is preserved in the raw record. No note is saved without confirmation; actual usage records show whether any cloud attempt occurred.",
            ]
        if identifier in {"A03", "A07"}:
            lines += [
                "",
                "A fresh login and follow-up planning session also inspected memory; compare memory_before, memory_after and memory_next_session in the raw records.",
            ]
    lines += [
        "",
        "## Matched cloud/local task comparison",
        "",
        "Three task types × three fixed public prompts × two providers × two repeats = 36 executions. Both providers receive the same schema/payload for each task. No private input is sent to cloud for this comparison. The independent scorer checks requested tier/cadence and ID sets, city+price+hours query content, or exact structured preference values. This static selection schema intentionally also tests schema-following limitations; application planning uses a stronger contextual schema.",
        "",
        "| Provider | Tasks passed | p50 / p95 seconds | Reported input / output tokens | Unknown-usage attempts |",
        "|---|---:|---:|---:|---:|",
    ]
    for provider in ["cloud", "local"]:
        rows = [r for r in providers if r["provider"] == provider]
        u = [x for r in rows for x in r["usage"]]
        metrics["providers"][provider] = {
            "passed": sum(r["success"] for r in rows),
            "n": len(rows),
            "p50_seconds": percentile([r["elapsed_seconds"] for r in rows], 0.5),
            "p95_seconds": percentile([r["elapsed_seconds"] for r in rows], 0.95),
        }
        m = metrics["providers"][provider]
        lines.append(
            f"| {provider} | {percentage(m['passed'], m['n'])} | {m['p50_seconds']:.2f} / {m['p95_seconds']:.2f} | {sum(x['input_tokens'] or 0 for x in u)} / {sum(x['output_tokens'] or 0 for x in u)} | {sum(x['input_tokens'] is None or x['output_tokens'] is None for x in u)} |"
        )
    lines += [
        "",
        "## Operational and source edge cases",
        "",
        "| Case | Passed | Observation |",
        "|---|---|---|",
    ]
    for r in operations:
        description = json.dumps(r.get("observation", {}))
        if len(description) > 400:
            description = description[:400] + "… (full record linked)"
        lines.append(
            f"| {r['id']} | {r['success']} | {description if r['success'] else r.get('detail', r.get('error'))} |"
        )
    lines += [
        "",
        "O01 terminates and replaces the actual serving process; O10 terminates the actual owning PostgreSQL backend and confirms zero ledgers before authorized recovery and exactly one afterward. O06 is explicitly a simulated cloud-429 fault with actual local inference, not a prompt-injection attack. O12 failed because planning returned PROVIDER_UNAVAILABLE after restart; it is retained as an end-to-end failure. The video separately demonstrates saved preferences reloaded on a new boot/login and a completed ledger.",
        "",
        "| City | Source check | Success | Error |",
        "|---|---|---|---|",
    ]
    for r in live:
        lines.append(f"| {r['city']} | {r['kind']} | {r['success']} | {r.get('error', '')} |")
    lines += [
        "",
        "All three cities completed actual Tavily MCP discovery. The remaining page-fetch failure is recorded, not promoted to a verified fact. Discovery checks test availability, not numerical claim verification. The corpus source-span review is a separate process.",
        "",
        "Additional browser evidence covers desktop 1440×1100 and mobile 390×844, no JavaScript errors/overflow, and an actual approved ledger. `cloud-smoke-v1.json` records an actual IAM-authenticated Cloud Run/Cloud SQL plan, approval and commit, plus fail-closed private notes with no laptop bridge. Anonymous requests are denied/masked (404 from the private Cloud Run route); the saved IAM policy has no allUsers grant. The earlier cloud smoke completed the flow but used an overly narrow assertion requiring 403 and is preserved.",
        "",
        "## Tokens consumed per planning session",
        "",
        "A session here is one planning episode including query rewrite, specialists, repairs and provider fallback. Benchmark runs stop at approval, so they contain no human resume cost. Provider-reported input/output counts are summed; separately reported reasoning is stored without adding it to output twice. Unknown failed attempts are **not zero consumption**: a conservative reservation is shown separately. Standalone restricted-note preprocessing is measured separately and was not used by these benchmark inputs. [Per-session table](evidence/session-tokens.json) and [every usage row](evidence/benchmark-usage.json) support the aggregates.",
        "",
        "| Session class | n | Mean reported input | Mean reported output | p50 / p95 reported total | Unknown attempts / reserved tokens |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for condition in ["baseline", "corrected"]:
        rows = [r for r in sessions if r["condition"] == condition]
        totals = [r["input_tokens_reported"] + r["output_tokens_reported"] for r in rows]
        lines.append(
            f"| {condition}, all admitted/validation cases | {len(rows)} | {statistics.mean(r['input_tokens_reported'] for r in rows):.1f} | {statistics.mean(r['output_tokens_reported'] for r in rows):.1f} | {percentile(totals, 0.5)} / {percentile(totals, 0.95)} | {sum(r['unknown_usage_attempts'] for r in rows)} / {sum(r['unknown_usage_reservation'] for r in rows)} |"
        )
    lines += [
        "",
        "### Deployment and operating cost per week",
        "",
        "Dated estimate: 25 November 2026, us-central1 (Iowa), USD, 168 hours/week, 730 hours/month conversion. Gross on-demand forecast; no trial credits, student/free tiers or discounts are subtracted. Actual invoice/billed USD was unavailable and is not claimed. Assumptions: one SQL micro, 10 GB SSD + 1 GB backup, 100 planning sessions/week averaging 30 active seconds at 2 vCPU/2 GiB, 1,000 HTTP requests/week, 3 GB registry, and 1 GB network allowance. This is a budget model, not a measured production workload.",
        "",
        "| Deployment component | Unit basis / formula | USD/week |",
        "|---|---|---:|",
        "| SQL compute | $0.0105/h × 168 | 1.7640 |",
        "| SQL SSD | assumed regional $0.17/GB-month × 10 × 168/730 | 0.3912 |",
        "| Backup | assumed $0.08/GB-month × 1 × 168/730 | 0.0184 |",
        "| Cloud Run CPU | $0.000024/vCPU-s × 2 × 3,000s | 0.1440 |",
        "| Cloud Run memory | $0.0000025/GiB-s × 2 × 3,000s | 0.0150 |",
        "| Requests | $0.40/million × 1,000 | 0.0004 |",
        "| Registry storage | assumed $0.10/GB-month × 3 × 168/730 | 0.0690 |",
        "| Network allowance | assumed 1 GB × $0.12/GB | 0.1200 |",
        "| **Deployment total** | sum, rounded | **2.52** |",
        "",
        "Published compute/request price references: [Cloud SQL](https://cloud.google.com/sql/pricing), [Cloud Run](https://cloud.google.com/run/pricing). Storage, backup, registry and egress rows are explicitly labeled conservative unit assumptions; region/usage can change them. The shared-core SQL tier has no SLA. SQL remains billable while provisioned even when Cloud Run scales to zero.",
        "",
        "Separate usage forecast: 100 sessions × 14,000 cloud input / 1,500 output tokens at **assumed budget rates**, $0.30/$0.90 per million = **$0.555/week** (about $0.00555/session). These are a planning allowance, not a published NVIDIA model price; developer credits/rate limits and unknown failed usage mean actual provider billing cannot be inferred from tokens. Substitute the account contract rates. Local inference has no per-token API charge; assumed 15W × 14h/week × $0.30/kWh = **$0.063/week**, excluding owned hardware/amortization.",
        "",
        "Search forecast: 300 basic calls/week × one credit × [$0.008/credit PAYG](https://www.tavily.com/pricing) = **$2.40/week** before any included credits. Conservative **all-in forecast ≈ $5.54/week** = deployment 2.52 + model allowance 0.555 + local electricity 0.063 + search 2.40. Build minutes, log volume beyond included allowances, tax, hardware and paid private-network services are unmeasured/excluded. More model-active time or retries raises the forecast; 10× traffic is not a promise of 10× unchanged latency.",
        "",
        "## Significant failures, fixes and remaining limitations",
        "",
        "| Failure / trigger | Implemented mitigation or reason deferred |",
        "|---|---|",
        "| Checkpoint/business writes raced on one async SQL session during development | Share a reentrant async lock with the official saver; regression verifies serialized pipeline use |",
        "| Open city dictionary produced a generic Activities key; specialists invented route IDs | Contextual city properties and ID enums for supervisor; reject/trace noncatalog advisory IDs |",
        "| Repair recopied malformed or unaffordable choices | Bounded tool validates alternatives; real model selects an indexed candidate; still reconstruct/recheck |",
        "| Shortened worker payload referenced a field absent from compact catalog | Corrected payload; complete regression suite passes; partial failed runs retained as development evidence |",
        "| NVIDIA JSON/schema failures, rate limits, local contention/context or unavailable endpoint | At most one compatible public-provider fallback, persistent budgets, explicit failure. Advisory worker can degrade visibly; supervisor failure still prevents certification. Final failures retained |",
        "| Tavily MCP rejected unsupported include_answer parameter | Removed unsupported argument; reran all six source checks; three real searches now succeed |",
        "| Official page refuses/redirects or changes markup | No automatic source promotion; explicit fetch failure/estimate state and narrow span review |",
        "| O12 restart test reached provider failure | Saved state is durable, but end-to-end planning failed and is scored false; video separately shows a successful real restart/memory/approval interaction |",
        "| Public Cloud Run request rejected by automatic approval review | Safer IAM-restricted deployment; no public allUsers grant. No live app URL is required for grading |",
        "| DNS rebinding/session compromise/publisher trust and long-term drift | Residual risks documented; transport DNS pinning, enterprise auth/RLS, source freshness automation and HA restore drills are future work |",
        "",
        "The system certifies only declared planning constraints against its dated catalog/estimates. It cannot guarantee ticket availability, final real-world prices, dietary suitability of a specific restaurant, holiday opening changes or an accessible route. No A2A protocol, payment, booking, arbitrary execution or fully bridged cloud/local deployment is claimed.",
        "",
        "## Reproduction and submission boundaries",
        "",
        "See README for locked setup and harness commands. Evidence is self-contained JSON/JSONL rather than expiring hosted trace links. The video shows all five claimed features and an engaged guardrail with actual runtime responses. The slide deck covers architecture, capabilities/limits, safety, metrics and future work. The personal process log remains an explicitly marked review draft; the student must confirm understanding/reflection. Brightspace upload and grader access cannot be certified from local package checks.",
    ]
    Path("deliverables/EVALUATION_REPORT.md").write_text("\n".join(lines) + "\n")
    Path("deliverables/metrics.json").write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
