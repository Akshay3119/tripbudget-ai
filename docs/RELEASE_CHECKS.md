# Release verification

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
