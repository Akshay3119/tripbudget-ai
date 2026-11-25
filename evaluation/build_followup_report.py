"""Build release1.0.1 results from new real-run datasets, without replacing the1.0.0 evidence."""

import asyncio
import hashlib
import json
import statistics
import subprocess
from collections import Counter
from pathlib import Path

from tripbudget.persistence import Store
from tripbudget.settings import Settings
from .build_report import percentage, percentile
from .oracle import audit

ROOT = Path("deliverables/evidence")


def read(name):
    return [json.loads(s) for s in (ROOT / (name + ".jsonl")).read_text().splitlines()]


async def main():
    names = {
        "benchmark": ("benchmark-v101", 80),
        "providers": ("provider-comparison-v101", 36),
        "operations": ("operations-v101", 12),
        "fallback": ("fallback-v101", 3),
        "attacks": ("attacks-v101", 20),
    }
    data = {key: read(name) for key, (name, _) in names.items()}
    for key, (_, count) in names.items():
        assert len(data[key]) == count, (key, len(data[key]))
    source_paths = sorted(Path("src").rglob("*.py")) + [Path("pyproject.toml"), Path("uv.lock")]
    evaluated_sources = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
    for key, (name, _) in names.items():
        metadata = json.loads((ROOT / (name + ".metadata.json")).read_text())
        recorded = metadata.get("source_files") or metadata.get("release", {}).get("source_files")
        assert recorded == evaluated_sources, "Measured source identity mismatch: " + key
    baseline_hashes = {}
    for name in [
        "benchmark-v1.jsonl",
        "provider-comparison.jsonl",
        "operations.jsonl",
        "attacks-v1.jsonl",
        "live-sources-v1.jsonl",
    ]:
        path = ROOT / name
        original_result = await asyncio.to_thread(
            subprocess.run, ["git", "show", "0c4daf9:" + str(path)], capture_output=True, check=True
        )
        original = original_result.stdout
        assert original == path.read_bytes(), "Original evidence was modified: " + str(path)
        baseline_hashes[str(path)] = hashlib.sha256(original).hexdigest()
    baseline = read("benchmark-v1")
    original_requests = {r["case"]: r["request"] for r in baseline}
    for r in data["benchmark"]:
        assert r["request"] == original_requests[r["case"]], r["case"]
    catalog = json.loads(Path("corpus/catalog.json").read_text())
    store = Store(Settings())
    usage = []
    sessions = []
    audits = []
    for r in data["benchmark"]:
        rows = (
            await store.all(
                "SELECT id,task,provider,model,input_tokens,output_tokens,reasoning_tokens,reserved,reserved_output,latency_ms,success,error FROM model_usage WHERE episode=%s",
                (r.get("episode"),),
            )
            if r.get("episode")
            else []
        )
        usage.extend({"episode": r["episode"], **u} for u in rows)
        sessions.append(
            {
                "case": r["case"],
                "kind": r["kind"],
                "condition": r["condition"],
                "repeat": r["repeat"],
                "episode": r.get("episode"),
                "reported_input_tokens": sum(u["input_tokens"] or 0 for u in rows),
                "reported_output_tokens": sum(u["output_tokens"] or 0 for u in rows),
                "unknown_attempts": sum(
                    u["input_tokens"] is None or u["output_tokens"] is None for u in rows
                ),
                "unknown_reserved_tokens": sum(
                    u["reserved"] for u in rows if u["input_tokens"] is None or u["output_tokens"] is None
                ),
                "attempts": len(rows),
            }
        )
        proposal = r.get("state", {}).get("proposal")
        if proposal:
            audits.append(
                {
                    "case": r["case"],
                    "condition": r["condition"],
                    "repeat": r["repeat"],
                    "episode": r["episode"],
                    "errors": audit(r["request"], proposal, catalog),
                }
            )
    for name, value in [
        ("benchmark-usage-v101", usage),
        ("session-tokens-v101", sessions),
        ("independent-audits-v101", audits),
    ]:
        (ROOT / (name + ".json")).write_text(json.dumps(value, indent=2))
    metrics = {
        "release": "1.0.1",
        "date": "2026-11-25",
        "timezone": "America/Los_Angeles",
        "new_logical_units": 151,
        "counts": {key: len(value) for key, value in data.items()},
        "planning": {},
        "providers": {},
        "baseline_evidence_sha256": baseline_hashes,
        "evaluated_source_files": evaluated_sources,
        "independent_audits": {"passed": sum(not r["errors"] for r in audits), "n": len(audits)},
    }
    lines = [
        "# TripBudgetAI 1.0.1 — provider reliability follow-up",
        "",
        "**Date:** 25 November 2026 (America/Los_Angeles). This is a new release evaluation. The original [1.0.0 report](EVALUATION_REPORT.md) and all original raw datasets remain unchanged apart from a navigation notice in the report. They are not retrospectively rescored.",
        "",
        "## Failures traced to their causes",
        "",
        "- Original corrected F01 repeat2 (`bd05142857304b018d7e108ddb60d589`) and F03 repeat2 (`a97ec0b377ee47319d514d6a1a6b01b8`) received real NVIDIA HTTP429 responses. Their MLX local fallback then produced invalid JSON or exceeded its request timeout. O12 (`78ecc2eaf69840f0a4e2fed0250d9ee3`) failed the same way after preferences had already persisted/restored.",
        "- Six original local matched tasks also failed: the MLX output omitted or mis-keyed candidate pools, copied defaults, or exhausted output with invalid JSON. Simply receiving HTTP200 from a model was insufficient evidence of a usable response.",
        "- Development probes uncovered two further interface details: JSON-object mode did not enforce required fields; NVIDIA native JSON-schema mode rejects the `uniqueItems` keyword. Intermediate unsuccessful real runs are preserved under `evidence/development/provider-comparison-v101*`, excluded from final rates.",
        "",
        "## Implemented fixes",
        "",
        "1. Pin `gemma4:e4b-it-q4_K_M` via the distinct `tripbudget-gemma4-e4b-gguf` alias. Before sending a local prompt, verify the configured model reports GGUF; an unverified/MLX backend is refused. Historical MLX aliases/records were not overwritten. [Official model tags](https://ollama.com/library/gemma4/tags) distinguish these variants; [upstream MLX reports](https://github.com/ollama/ollama/issues/17933) provided background, while the failure traces and real reruns establish this application diagnosis.",
        "2. Use native NVIDIA `json_schema` output and native Ollama schema output, then independently validate every response with the full JSON schema and Pydantic. All fields must be explicit: omitted defaults are rejected rather than silently filled. Truncated output is rejected and its reported usage still charged. The decoder projection omits unsupported `uniqueItems`; the full client contract still enforces uniqueness. [NVIDIA structured-output guidance](https://docs.nvidia.com/nim/large-language-models/2.0.10/get-started/advanced/get-started-nemotron-3.5-lightning) and [Ollama guidance](https://docs.ollama.com/capabilities/structured-outputs) describe the provider interfaces.",
        "3. Production and matched evaluation share a contextual candidate contract: every catalog ID for a requested city appears exactly once in its ranked candidate pool. Cadence separately controls scheduled activities. This fixes the one-activity/day versus one-candidate misunderstanding. The model still selects order, tier and cadence; the contract does not encode the scorer's requested economy/one-per-day answer.",
        "4. Compact only descriptive schema annotations in the prompt; all constraints/IDs/user fields and the full native/client contracts remain intact. This keeps the largest three-city request inside the original conservative 8192-token context check. Context skips are explicitly traced. Bound queue wait, backend inspection and generation inside the existing provider attempt deadline; retain the existing two-provider maximum, episode call/token/active-time limits and local-only privacy rule. No caps, approval checks, source validation or monetary checks were relaxed.",
        "5. Bound the non-authoritative expected_cost_cents estimate to 100,000,000 cents before checkpointing; an observed cloud value above 64-bit range previously caused a serializer TypeError. A regression now verifies rejection, fallback, checkpoint, human approval and commit. Unexpected worker exceptions also expose a safe recoverable EXECUTION_INTERRUPTED state instead of stale RUNNING; exception text is not echoed. O12 now records distinct checks for real process replacement, fresh login, restored preference version/values, application to a later request and successful valid planning. Failures retain episode/trace diagnostics. O09 also requires actual planning completion after reconnect, rather than only absence of an unauthorized ledger.",
        "",
        "## Method and comparability",
        "",
        "**151 new logical units, measured in the local evaluation environment with real NVIDIA calls and actual local inference:** 80 complete paired planning executions + 36 matched provider tasks + 12 operational checks + 20 real attack episodes + 3 injected-cloud-outage cases using actual local inference. The six original live-source checks were not rerun because publisher fetching/MCP code did not change; their one failed publisher fetch is still a known limitation. Additional development probes, browser/cloud checks and unit fixtures are not included in 151.",
        "",
        "Every original planning case ran again in both conditions with two repeats and the same grading criteria. The report verifies exact request equality to the original raw records and verifies the original raw-file hashes against committed baseline 0c4daf9. Conditions still use randomized order seed 599, temperature 0.2 and the same catalog. All failures are retained. All five suite metadata snapshots match the final application source/dependency hashes, as does the built container. New suite output paths/case snapshots prevent accidental overwrite.",
        "",
        "This is an application-release comparison, not an isolated model-quality experiment: the local quantization/backend and structured contracts changed, and final suites ran sequentially instead of the earlier concurrent development load. Two repeats remain a small sample. Latency and rate-limit differences cannot be attributed solely to one code change. Matched task prompts/oracles remain unchanged; the stronger shared application schema is explicitly part of the new adapter being evaluated.",
        "",
        "## Planning results",
        "",
        "| Condition | Feasible | Proven-infeasible | Missing data | p50 / p95 seconds | Repeat feasible rates |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for condition in ["baseline", "corrected"]:
        rows = [r for r in data["benchmark"] if r["condition"] == condition]
        m = {"outcomes": dict(Counter(r["outcome"] for r in rows))}
        cells = []
        for kind in ["feasible", "infeasible", "incomplete"]:
            chosen = [r for r in rows if r["kind"] == kind]
            m[kind] = {"passed": sum(r["success"] for r in chosen), "n": len(chosen)}
            cells.append(percentage(m[kind]["passed"], m[kind]["n"]))
        m["p50_seconds"] = percentile([r["elapsed_seconds"] for r in rows], 0.5)
        m["p95_seconds"] = percentile([r["elapsed_seconds"] for r in rows], 0.95)
        rates = [
            sum(r["success"] for r in rows if r["kind"] == "feasible" and r["repeat"] == i) / 12
            for i in [1, 2]
        ]
        m["repeat_feasible_rates"] = rates
        m["sample_sd_percentage_points"] = 100 * statistics.stdev(rates)
        metrics["planning"][condition] = m
        lines.append(
            f"| {condition} | {' | '.join(cells)} | {m['p50_seconds']:.2f} / {m['p95_seconds']:.2f} | {100 * rates[0]:.1f}% / {100 * rates[1]:.1f}% |"
        )
    lines += [
        "",
        f"Historical corrected feasible completion was 22/24; the new value above is a fresh measurement, not a replacement of the two old failures. Independent audits passed **{metrics['independent_audits']['passed']}/{len(audits)}** emitted proposals. Benchmark unapproved commits: **{sum(r.get('unsafe_commit', False) for r in data['benchmark'])}**. This is a commit-safety check; functional approval/commit is tested separately.",
        "",
        "| Original affected case | New corrected repeat 1 | Repeat 2 |",
        "|---|---|---|",
    ]
    for identifier in ["F01", "F03"]:
        rows = sorted(
            [r for r in data["benchmark"] if r["case"] == identifier and r["condition"] == "corrected"],
            key=lambda r: r["repeat"],
        )
        lines.append(
            f"| {identifier} | {rows[0]['outcome']} (`{rows[0]['episode']}`) | {rows[1]['outcome']} (`{rows[1]['episode']}`) |"
        )
    lines += [
        "",
        "## Matched provider tasks",
        "",
        "| Provider | Passed / n | p50 / p95 seconds |",
        "|---|---:|---:|",
    ]
    for provider in ["cloud", "local"]:
        rows = [r for r in data["providers"] if r["provider"] == provider]
        m = {
            "passed": sum(r["success"] for r in rows),
            "n": len(rows),
            "p50_seconds": percentile([r["elapsed_seconds"] for r in rows], 0.5),
            "p95_seconds": percentile([r["elapsed_seconds"] for r in rows], 0.95),
        }
        metrics["providers"][provider] = m
        lines.append(
            f"| {provider} | {percentage(m['passed'], m['n'])} | {m['p50_seconds']:.2f} / {m['p95_seconds']:.2f} |"
        )
    lines += [
        "",
        "The original scores were cloud 18/18 and local 12/18. Backend/model digest, runtime version, exact task/schema snapshots and source hashes are in the new metadata/cases sidecars. No result is mocked; fixture-based unit tests remain a separate verification layer.",
        "",
        "## Operational rerun and real fallback under an injected outage",
        "",
        "| Case | Passed | Observation |",
        "|---|---|---|",
    ]
    for r in data["operations"]:
        observation = r.get("observation", {})
        detail = (
            observation.get("outcome", observation.get("failure", "see full real-run record"))
            if r["success"]
            else r.get("detail", r.get("error"))
        )
        lines.append(f"| {r['id']} | {r['success']} | {detail} |")
    metrics["operations"] = {"passed": sum(r["success"] for r in data["operations"]), "n": 12}
    o12 = next(r for r in data["operations"] if r["id"] == "O12")
    lines += [
        "",
        "O12 actual observation:",
        "",
        "```json",
        json.dumps({k: v for k, v in o12.get("observation", {}).items() if k != "planning_run"}, indent=2),
        "```",
        "",
        "| Outage case | Completed | Independent audit errors | Seconds |",
        "|---|---|---|---:|",
    ]
    for r in data["fallback"]:
        lines.append(
            f"| {r['case']} | {r['success']} | {r['independent_audit_errors']} | {r['elapsed_seconds']} |"
        )
    metrics["fallback"] = {"passed": sum(r["success"] for r in data["fallback"]), "n": 3}
    lines += [
        "",
        "These are authenticated, explicitly simulated cloud 429 faults with actual GGUF completions, not prompt attacks or mocked model responses. They cover the original failing F01/F03 shapes and tight-walking F08. All provider/episode budgets stay unchanged. This verifies fallback handling; it does not mean NVIDIA stopped returning real 429s or that a cloud-only deployment has a laptop bridge.",
        "",
        "## Safety regression",
        "",
        "| Attack | Model-exposed /2 | Protected state /2 | Legitimate task /2 |",
        "|---|---:|---:|---:|",
    ]
    attacks = data["attacks"]
    for identifier in sorted({r["id"] for r in attacks}):
        rows = [r for r in attacks if r["id"] == identifier]
        lines.append(
            f"| {identifier} | {sum(r['model_exposed'] for r in rows)} | {sum(r['protected_state_unchanged'] for r in rows)} | {sum(r['legitimate_task_completed'] for r in rows)} |"
        )
    metrics["attacks"] = {
        "attempted": 20,
        "model_exposed": sum(r["model_exposed"] for r in attacks),
        "protected_state_unchanged": sum(r["protected_state_unchanged"] for r in attacks),
        "legitimate_task_completed": sum(r["legitimate_task_completed"] for r in attacks),
    }
    lines += [
        "",
        "All ten original attack types ran twice through real operating HTTP/retrieval/private-note surfaces. Full new payloads, model outputs, critic/approval events, memory checks and usage are preserved in [new attack traces](evidence/attacks-v101.jsonl). The [original report](EVALUATION_REPORT.md#real-prompt-injection-attacks) documents each payload/surface and implemented mitigation. Unexposed attempts are not counted as model resistance, and protected-state containment is not a universal semantic-refusal claim.",
        "",
        "## Tokens, attempts and cost",
        "",
        "| Class | n | Mean reported input / output | p50 / p95 reported total | Unknown attempts / reserved tokens |",
        "|---|---:|---:|---:|---:|",
    ]
    for label, rows in [
        ("baseline/all", [r for r in sessions if r["condition"] == "baseline"]),
        ("corrected/all", [r for r in sessions if r["condition"] == "corrected"]),
        (
            "corrected/feasible",
            [r for r in sessions if r["condition"] == "corrected" and r["kind"] == "feasible"],
        ),
    ]:
        totals = [r["reported_input_tokens"] + r["reported_output_tokens"] for r in rows]
        lines.append(
            f"| {label} | {len(rows)} | {statistics.mean(r['reported_input_tokens'] for r in rows):.1f} / {statistics.mean(r['reported_output_tokens'] for r in rows):.1f} | {percentile(totals, 0.5)} / {percentile(totals, 0.95)} | {sum(r['unknown_attempts'] for r in rows)} / {sum(r['unknown_reserved_tokens'] for r in rows)} |"
        )
    failures = Counter(u["error"] for u in usage if not u["success"])
    metrics["provider_attempt_errors"] = dict(failures)
    lines += [
        "",
        f"Observed failed provider attempts in the planning rerun: `{dict(failures)}`. These attempts remain visible even if the episode succeeds after fallback. Reported reasoning is not added to completion tokens twice. Unknown failed usage is not treated as zero consumption; conservative reservations remain. Fault-injected runs are separate from ordinary session usage and billing.",
        "",
        "Weekly deployment/operating costs remain estimates, not an invoice. The original dated us-central1 budget model gives **$2.52/week deployment** and **about $5.54/week all-in** at 100 sessions/week, 300 basic searches/week and its published/explicitly assumed units; see the [full formulas and sources](EVALUATION_REPORT.md#deployment-and-operating-cost-per-week). These forecasts assume 3GB retained registry storage and exclude hardware/amortization and unmeasured build/log overhead. Keeping more image versions costs extra (at the assumed $0.10/GB-month, about $0.069/week per extra 3GB). New measured token rows above replace guesses about session consumption; the model-dollar allowance is still an assumption, not an NVIDIA quote. SQL remains billable while provisioned.",
        "",
        "## Container and cloud deployment scope",
        "",
        "The linux/amd64 container passed local health/readiness and unauthenticated-API checks. Its 20 application/dependency identity hashes match the evaluated files; see [image identity](evidence/container-image-v101.json) and [startup check](evidence/container-startup-v101.json). IAM-private Cloud Run revision `a4-tripbudget-00003-jh7` serves the verified 1.0.1 image. The registry manifest links uploaded index digest `8dcebc06…` to deployed linux/amd64 digest `d29c2419…`; full identities and readiness are in [cloud release](evidence/cloud-release-v101.json). The [actual cloud smoke](evidence/cloud-smoke-v101.json) passed planning, authenticated human approval and ledger commit on 1.0.1; absent-laptop private notes returned 503 and anonymous invocation returned 404. [Deployment status](evidence/deployment-status-v101.json) and the [handoff](../HANDOFF.md#8-cloud-deployment-and-operations-context) record the explicit authorization and operating scope.",
        "",
        "The [fresh browser run](evidence/ui-v101/browser-results.json) also completed actual planning → human approval → ledger commit, with no JavaScript errors or mobile overflow and correct clearing of prior results after an infeasible new request. Desktop/mobile screenshots were inspected. These smoke/browser checks are separate from the 151 logical evaluation units.",
        "",
        "## Files and reproduction",
        "",
        "- [Planning](evidence/benchmark-v101.jsonl), [provider tasks](evidence/provider-comparison-v101.jsonl), [operations](evidence/operations-v101.jsonl), [outage fallback](evidence/fallback-v101.jsonl), [attacks](evidence/attacks-v101.jsonl).",
        "- [Per-session tokens](evidence/session-tokens-v101.json), [all benchmark usage](evidence/benchmark-usage-v101.json), [independent audits](evidence/independent-audits-v101.json). Metadata/case sidecars record actual backend and source identity.",
        "- `evaluation.run_followup` runs the affected suites sequentially after the 36-task provider gate. Individual runners accept new output paths. Existing raw files are never overwritten; see the updated handoff for fresh-run commands and setup.",
        "",
        "Both providers can still be unavailable, and the cloud-only deployment still lacks a laptop bridge. In those cases explicit bounded failure is appropriate; budgets/privacy/approval must not be bypassed. Source availability, DNS trust, HA/load certification and the personal process-log review remain outside this provider fix. The original video/slide measurements are historical 1.0.0 evidence unless explicitly replaced by a labeled 1.0.1 artifact.",
    ]
    Path("deliverables/EVALUATION_FOLLOWUP_1.0.1.md").write_text("\n".join(lines) + "\n")
    Path("deliverables/metrics-v101.json").write_text(json.dumps(metrics, indent=2) + "\n")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
