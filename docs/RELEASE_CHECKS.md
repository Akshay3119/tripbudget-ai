# Release verification

Current provider/operational release: **1.0.1**. See [the separately measured follow-up](../deliverables/EVALUATION_FOLLOWUP_1.0.1.md) and [contributor handoff](../HANDOFF.md). Original failures below remain historical evidence.

**Subsequent access change — 25 November 2026:** the owner requested public invocation. Anonymous website/readiness 200, protected metadata/preferences 401, and actual browser application sign-in passed without Google Cloud headers. See `deliverables/evidence/public-access-20261125.json`. The private-ingress checks below describe the initial rollout.

## Current 1.0.1 checks

| Layer | Observed result | Evidence |
|---|---|---|
| Static / fast regressions | Ruff passed; **92 tests passed** | `deliverables/evidence/lint-v101.txt`, `pytest-v101.txt` |
| Paired planning | 80 executions; corrected feasible **24/24** vs baseline **4/24**; infeasible/missing data **8/8 each per condition**; zero unapproved commits | `deliverables/evidence/benchmark-v101.jsonl` |
| Matched providers | **36/36**, cloud/local **18/18 each** | `deliverables/evidence/provider-comparison-v101.jsonl` |
| Operational faults | **12/12**, including actual completion after preferences survive replacement | `deliverables/evidence/operations-v101.jsonl` |
| Forced cloud outage / real local model | **3/3**, original failing shapes and tight walking, independent oracle accepts all | `deliverables/evidence/fallback-v101.jsonl` |
| Independent proposals | **28/28** emitted plans pass separate accounting/window audits | `deliverables/evidence/independent-audits-v101.json` |
| Real attack rerun | **20/20** protected state, **20/20** legitimate completion, **14** model-exposed attempts | `deliverables/evidence/attacks-v101.jsonl` |
| Actual browser | Plan → approval → ledger, desktop/mobile visual check, no JS errors or overflow; new infeasible input clears prior result | `deliverables/evidence/ui-v101/browser-results.json` |
| Built container | Evaluated application/lock hashes match linux/amd64 image; local health/readiness/auth checks pass | `container-image-v101.json`, `container-startup-v101.json` |
| Cloud rollout | IAM-private 1.0.1 revision `a4-tripbudget-00003-jh7`; actual plan → approval → ledger; private notes 503 / anonymous 404 | `deliverables/evidence/cloud-release-v101.json`, `cloud-smoke-v101.json` |

The 1.0.1 results supplement the original release. Video/slide metrics remain explicitly historical. The current report records all attack rerun and independent-audit denominators separately.

## Historical 1.0.0 checks

25 November 2026. These observations are backed by the linked local evidence; they are not claims about every possible input/provider condition.

| Layer | Observed result | Evidence |
|---|---|---|
| Static check | Ruff passed | `deliverables/evidence/lint.txt` |
| Automated regressions | 71 passed, including integer/odd-cent allocation, room occupancy, missing costs, source tampering, ownership, replay and saved-preference idempotency | `deliverables/evidence/pytest.txt` |
| Independent witnesses | 12/12 feasible cases have an independently audited witness | `evaluation/witnesses.json` |
| Paired benchmark | Corrected feasible22/24 vs baseline4/24; infeasible8/8 and missing-data8/8 per condition | `deliverables/metrics.json` |
| Actual prompt attacks | 20 attempts,13 model-exposed; protected state20/20, legitimate utility19/20 | `deliverables/evidence/attacks-v1.jsonl` |
| Matched providers | Cloud18/18, local12/18 | `deliverables/evidence/provider-comparison.jsonl` |
| Operating/fault cases | 11/12; failed planning on O12 retained despite restored preference state | `operations.jsonl`, `memory-restart-inspection.json` |
| Current sources | 5/6; three actual MCP searches succeed; one direct publisher fetch fails | `live-sources-v1.jsonl` |
| Final browser | Real planning/approval/ledger, desktop/mobile, no JS errors or overflow; old results cleared on new infeasible input | `deliverables/evidence/ui/browser-results.json` |
| Actual recording | 425s,1440×1000,H.264/AAC; real repair, local/cloud calls, restart/memory/HITL and guardrail | `recorded-run.json`, `recording-events.json`, `docs/recording-evidence.md` |
| Playback | Real Chromium seek and playback advance, readyState4/no error; full ffmpeg decode and audio check | `deliverables/evidence/video-playback.json` |
| Presentation | 16 native editable slides, every rendered slide visually reviewed; PDF snapshot re-render checked | `deliverables/TECHNICAL_PRESENTATION.md` |
| Deployment | IAM-private final Cloud Run revision, actual Cloud SQL approval/ledger flow, absent-laptop private notes fail closed | `cloud-smoke-release.json`, `cloud-release-revision.json` |
| Package | Exact source symbol/range resolution, all artifacts, video duration and configured-secret exclusions | `deliverables/evidence/package-verification.json` |

The model failure cases remain failures. A safe refusal is not a successful feasible trip. No claim is made that a private repository is already shared with unidentified graders or that Brightspace submission is complete. The individual process log is a review draft pending the student's own reflection/understanding.
