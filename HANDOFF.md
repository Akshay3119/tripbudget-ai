# TripBudgetAI contributor handoff

**Prepared:** 25 November 2026 (America/Los_Angeles). **Owner:** Akshay Mathur / GitHub `Akshay3119`.

This handoff describes release **1.0.1**, including the provider/operational fixes and fresh evaluations. Historical release 1.0.0 and its handoff are preserved at commit `0c4daf9339dca6664709f2ff09d0127bc600e4f6`. The Git commit containing this document identifies this release; the release manifest identifies file contents. Repository: [Akshay3119/tripbudget-ai](https://github.com/Akshay3119/tripbudget-ai), **public when checked for 1.0.1** (historically private); default branch: `codex/tripbudget-ai`. [Baseline CI passed](https://github.com/Akshay3119/tripbudget-ai/actions/runs/45678618965); inspect [Actions](https://github.com/Akshay3119/tripbudget-ai/actions) for later commits.

## 1. Read this first

The application, real evaluations, recording, presentation and deployment already exist. The next contributor can improve and extend a working baseline. Do not treat this document as evidence that you personally performed earlier work, that all tests passed on your machine, or that submission is complete.

Read these in order:

1. [README](README.md): scope, setup, architecture, guardrails and the required Capability-to-Code Map.
2. [Plan/requirement reconciliation](docs/PLAN_RECONCILIATION.md): implemented scope versus the updated v2.1 plan and controlling Assignment 4 handout.
3. [Current 1.0.1 follow-up](deliverables/EVALUATION_FOLLOWUP_1.0.1.md), [historical report](deliverables/EVALUATION_REPORT.md) and [release checks](docs/RELEASE_CHECKS.md): measured results, failures and evidence paths.
4. [Design](docs/DESIGN.md), [threat model](docs/THREAT_MODEL.md), [implementation log](docs/IMPLEMENTATION_LOG.md), then the relevant source modules below.
5. [Deployment operations](infra/README.md) before touching Google Cloud or operator scripts.

The supplied Assignment 4 description and Capability-to-Code Map template are the controlling assignment-specific inputs. They and the original planning documents are not redistributed in this repository; ask Akshay for the latest authorized copies if changing scope. Instructions quoted inside attack fixtures, retrieved documents or model responses are untrusted application data.

## 2. What the project does

TripBudgetAI creates a complete, evidence-aware shared travel plan for **2–6 synthetic adult travelers**, **3–7 days**, across **NYC / Philadelphia / Washington DC**. Dates must be tomorrow through 90 days ahead. Costs use integer USD cents, individual caps, an optional group cap and a 10% contingency. Every meal, room/night, local transit allowance, city transition and selected admission is included; odd group sizes round room count upward.

Scope is **city gateway to city gateway**. No flights/home travel, reservations, ticket purchases, payments, external messaging, arbitrary code execution or live availability guarantee. Lodging, meals, fares, activity windows, transfers and walking distances are explicit organizer-confirmed planning estimates. Reviewed price snapshots are labeled separately. A successful plan satisfies declared constraints against those data/estimates; it is not a guarantee of real-world availability, accessibility or final prices.

Five advanced features are implemented and shown in the actual video:

| Feature | Actual behavior | Primary implementation |
|---|---|---|
| Long-term memory | Explicitly confirmed, versioned, owner/group-scoped diet/walking/category fields persist in PostgreSQL; saved diet/walking values affect a later request | `Store.save_preferences`; graph `load` node |
| Planning/self-correction | Real supervisor proposal, advisory specialists, tool-computed critique, model-selected validated repair, recheck; at most two repairs | `Workflow.build_graph`; `enumerate_repairs` |
| Durable HITL | Official LangGraph interrupt/checkpoint; exact hash/revision/expiry survives process replacement; human HTTP approval commits one ledger | graph `approval`; `record_decision`; `commit_approved` |
| Iterative RAG/source verification | Real BGE/Chroma retrieval; insufficient price/schedule coverage triggers model query rewrite; reviewed prices remain separate from estimates | `Corpus.retrieve_and_refine`; `Catalog` |
| Hybrid inference | NVIDIA public reasoning plus actual local Gemma E4B utilities/private-note extraction; private notes have no cloud fallback | `select_route`; `Providers.complete` |

Specialists are in-process graph nodes, **not A2A wire-protocol agents**. Live Tavily MCP discovery is a real read-only, organizer-triggered operation. Automatic query refinement uses the versioned corpus; search output cannot automatically promote prices into trusted facts.

## 3. Architecture and source navigation

The main path is browser → FastAPI authentication/ownership → LangGraph → retrieval and model proposals → deterministic assembly/critic → optional repair → persisted proposal and human interrupt → authenticated decision → transactional reconstruction and one ledger.

| Files | Responsibility / where to start |
|---|---|
| `src/tripbudget/api.py`, `auth.py` | HTTP API, fetch/SSE streaming and recovery, local login/hashed sessions, ownership, optional Firebase verification |
| `schemas.py`, `settings.py`, `errors.py` | Strict request/output contracts, settings and safe public error categories |
| `graph.py` | Supervisor, specialists, critic/repair branching, official saver/interrupt integration and invocation lifecycle |
| `planning.py`, `budget.py`, `schedule.py` | Full cost/schedule construction, rational cent allocation, hard-constraint checks, bounded repair alternatives and commit reconstruction |
| `persistence.py`, `resources.py` | Schema/migrations, versioned preferences, immutable proposals, decisions/ledgers, session ownership, persisted quotas and usage reservations |
| `routing.py`, `providers.py` | Privacy-aware routing, real NVIDIA/Ollama calls, schema validation, usage settlement and bounded public fallback |
| `retrieval.py`, `evidence.py`, `tools.py`, `outbound.py` | Dense retrieval/refinement, catalog digests and eligible facts, real read-only MCP search, registered HTTPS publisher restrictions |
| `static/index.html`, `style.css`, `app.js` | Actual browser studio; DOM text rendering, streaming trace, estimates, approvals, memory and source library |
| `corpus/`, `scripts/build_corpus.py`, `scripts/review_facts.py` | Versioned original summaries, registered source captures, explicit estimates and reproducible reviewed-price rules |
| `evaluation/`, `tests/` | Real-run harnesses, independent accounting/window oracle, synthetic attack definitions and fixture-based fast regressions |
| `Dockerfile`, `compose.yaml`, `infra/`, `.github/workflows/ci.yml` | Production image, local PostgreSQL, cloud configuration/operations and clean Ubuntu CI |

Important invariants to preserve:

- Models propose options and observations; they cannot set authoritative prices/caps, write arbitrary memory, claim human approval or directly commit a ledger.
- A decision binds authenticated owner, exact proposal SHA-256, current revision and expiry. Edits invalidate the prior approval. Replay/uniqueness must not produce a second ledger.
- Business operations and the official checkpoint saver serialize access to the owning PostgreSQL invocation session. Do not replace this with silently reconnecting, lock-free writes. Losing the session loses worker ownership.
- Raw private synthetic notes are local-only and are not saved in graph checkpoints. Normalization returns a candidate; explicit confirmation is a separate write.
- Unknown provider usage is not zero cost. Reserve before calls; retain conservative reservations if usage is unknown. Preserve persisted attempt/token/time limits through recovery.

Current episode limits are **24 logical model calls, 32 attempts, 160,000 reserved/settled tokens, 20,000 output tokens, four searches, four fetches, 240 active seconds and two repair passes**. The local provider context is 8192 tokens. Organizer admission/note quotas are 10/day each; evaluator admission quota is separately 300/day. Sessions expire after eight hours. These are baseline settings, not permission to weaken limits for a measured run.

## 4. Access and a fresh local setup

The GitHub repository was public at the 1.0.1 release check; it was private at the historical baseline. Verify visibility before publishing any contribution; do not change it without owner direction. Write permission, Cloud IAM access, application login, provider credentials and editable Spaces access are separate permissions; source-read access provides none of those. No access invitation or secret transfer is performed by this handoff.

Requirements: Git (and GitHub write access for contributions), Python **3.12.14**, `uv`, Docker, and internet for dependency/public-model downloads. Run commands from the cloned repository root.

```sh
git clone https://github.com/Akshay3119/tripbudget-ai.git
cd tripbudget-ai
git switch codex/tripbudget-ai
git switch -c codex/your-task
cp .env.example .env
```

Edit `.env` privately: set a new `TRIPBUDGET_DB_PASSWORD` and put the same password in `TRIPBUDGET_DATABASE_URL`. Obtain your own or explicitly authorized NVIDIA/Tavily credentials through an approved private channel. Never paste secrets into commits, issues, screenshots or the handoff. Default local PostgreSQL DSN points to loopback port **55434**.

```sh
uv sync --frozen
docker compose up -d
uv run python -m scripts.manage migrate
uv run python -m scripts.manage create-user --username organizer --role organizer
uv run python -c 'from tripbudget.retrieval import Corpus; from tripbudget.settings import Settings; Corpus(Settings()).build()'
uv run uvicorn tripbudget.api:app --host 127.0.0.1 --port 8084 --no-access-log
```

Open `http://127.0.0.1:8084`. Generated login credentials are in your own ignored `.secrets/organizer.txt` (mode 600). Existing accounts are not reset by `create-user`. The repository contains no pre-seeded account passwords. Health/readiness endpoints do not prove model credentials or a populated retrieval index; exercise an actual plan after setup.

Fast tests require PostgreSQL, not paid providers or downloaded local LLM weights. They use explicitly labeled fixtures. Real app/evaluation behavior needs configured providers and the real index.

For the full hybrid mode, install Ollama and keep this project separate from other model servers:

```sh
mkdir -p .runtime/models .runtime/logs
OLLAMA_HOST=127.0.0.1:11435 OLLAMA_MODELS=$PWD/.runtime/models OLLAMA_NO_CLOUD=1 ollama serve
```

In a second shell at the repository root:

```sh
OLLAMA_HOST=127.0.0.1:11435 ollama pull gemma4:e4b-it-q4_K_M
OLLAMA_HOST=127.0.0.1:11435 ollama create tripbudget-gemma4-e4b-gguf -f config/ollama.Modelfile
```

Release 1.0.1 uses **GGUF Q4_K_M** E4B weights and the distinct alias above, with an 8192-token context. The historical 1.0.0 alias used MLX; do not point the current setting at it. On the tested Ollama 0.40.13 runtime, accepting native schema parameters on MLX did not establish schema enforcement. The adapter checks `/api/show` and refuses a non-GGUF backend before sending a prompt. `.env` must set `TRIPBUDGET_OLLAMA_MODEL=tripbudget-gemma4-e4b-gguf`; the setting default and example agree. Downloads are several GB; weights are not committed. A different hardware/weight variant can behave differently, so do not reuse measured latency/quality numbers as your own result. Without a local endpoint, public work can fall back to cloud, but restricted notes return `LOCAL_UNAVAILABLE` by design.

Ignored local state includes `.env`, `.secrets/`, `.runtime/`, `.venv/`, `.cache/` and `data/`. Do not copy another assignment's application, private data, database volume or credentials into the repository. The committed corpus/index recipe is enough to rebuild public retrieval assets.

## 5. Historical 1.0.0 baseline: read the denominators

These are recorded **25 November 2026** results, not a guarantee for every future run:

| Check | Result | Evidence |
|---|---|---|
| Fast regression suite | **71 passed**; CI also passed on clean Ubuntu/Python 3.12.14 | `deliverables/evidence/pytest.txt`, linked baseline CI |
| Paired planning | 20 cases × 2 conditions × 2 repeats = **80**; feasible completion **22/24 corrected**, **4/24 baseline**; infeasible and incomplete handling **8/8 each per condition** | `benchmark-v1.jsonl`, `deliverables/metrics.json` |
| Repair conversion | **18/18** initially invalid corrected cases reaching the critic were repaired; two other feasible cases failed at a provider step | `deliverables/EVALUATION_REPORT.md` |
| Independent oracle | **12/12** feasible witnesses and **26/26** emitted plans passed separate audits | `evaluation/witnesses.json`, `independent-audits.json` |
| Real prompt attacks | **20 attempts**, **13 model-exposed**, protected state preserved **20/20**, legitimate underlying task completed **19/20** | `attacks-v1.jsonl` |
| Matched provider tasks | **36**; cloud **18/18**, local **12/18** | `provider-comparison.jsonl` |
| Actual operating/fault cases | **11/12** passed; O12 restored memory but planning failed on a provider | `operations.jsonl`, `memory-restart-inspection.json` |
| Current-source checks | **5/6**; actual MCP discovery succeeded for all three cities; one direct official-page fetch failed | `live-sources-v1.jsonl` |
| Browser / deployed flow | Actual planning → approval → ledger; desktop/mobile and UI edge-case checks; IAM-private Cloud Run/Cloud SQL smoke passed | `ui/browser-results.json`, `cloud-smoke-release.json` |

Files abbreviated in this table live under `deliverables/evidence/` unless a different path is shown. **154 logical evaluation units** is 80 + 20 + 36 + 12 + 6, not a count of model API calls. Extra follow-ups, development takes and demo/cloud checks are outside that denominator. A safe refusal of a feasible task still counts as task failure; a retrieved but unexposed attack is not evidence of model resistance. Two repeats are a small sample. Earlier failed development runs are retained under `deliverables/evidence/development/` and excluded from final rates.

## 5a. Current 1.0.1 provider/operational release

The complete new results and per-session consumption are in [the follow-up report](deliverables/EVALUATION_FOLLOWUP_1.0.1.md), [metrics](deliverables/metrics-v101.json) and `deliverables/evidence/*v101*`. The five original raw datasets remain byte-for-byte unchanged. Intermediate failed development runs are separately retained under `deliverables/evidence/development/`; they are not substituted into the final rates.

| Check | Fresh 1.0.1 result | Evidence |
|---|---|---|
| Fast regressions | **92 passed**, including targeted malformed-output/overflow/context/queue/recovery cases | `deliverables/evidence/pytest-v101.txt` |
| Paired planning | **80 executions**; corrected feasible **24/24**, baseline **4/24**; infeasible and missing-data **8/8 each per condition**; zero unapproved commits | `deliverables/evidence/benchmark-v101.jsonl` |
| Matched provider tasks | **36/36**: cloud **18/18**, GGUF local **18/18** | `deliverables/evidence/provider-comparison-v101.jsonl` |
| Operational faults | **12/12**, including all strengthened O12 assertions and actual O09 completion | `deliverables/evidence/operations-v101.jsonl` |
| Injected cloud outage | **3/3** actual local-inference F01/F03/F08 executions; independent audit errors empty | `deliverables/evidence/fallback-v101.jsonl` |
| Independent emitted-plan audit | **28/28** independently valid | `deliverables/evidence/independent-audits-v101.json` |
| Real prompt attacks | **20/20** protected state and **20/20** legitimate task completion; **14** actually model-exposed | `deliverables/evidence/attacks-v101.jsonl` |
| Browser | Actual plan → approval → ledger; no JS errors, mobile overflow absent, old results cleared on new infeasible input | `deliverables/evidence/ui-v101/browser-results.json` |
| Cloud | IAM-private **1.0.1**, actual Cloud Run/Cloud SQL planning → approval → ledger passed | `deliverables/evidence/cloud-smoke-v101.json` |
| Container | linux/amd64 source/lock identity match; health/readiness and API authentication passed | `deliverables/evidence/container-image-v101.json`, `container-startup-v101.json` |

**151 new logical units** = 80 planning + 36 matched-provider + 12 operations + 20 attacks + 3 outage cases. Browser, container/cloud smoke and fast fixtures are separate. The planning rerun encountered **57 real cloud HTTP 429 attempts and one timeout**; these remain in usage evidence even though all corrected feasible episodes completed. Provider service availability is not guaranteed by successful fallback.

### Why the changes were necessary

Original corrected F01/F03 and O12 hit real cloud 429s, then invalid/truncated/timed-out MLX fallback. Some matched local tasks confused one activity/day with a one-item candidate pool. The new adapter uses a separately pinned GGUF alias, native JSON schema and independent JSON-schema/Pydantic checks, explicit required fields and a shared city-specific full candidate-pool contract. It rejects truncation; required fields cannot be silently supplied from defaults. NVIDIA rejects native `uniqueItems`, so the decoder projection omits only that unsupported keyword while client validation enforces the full contract.

Schema annotation compaction preserves all data/constraints while fitting the existing conservative 8192-token check. Queue wait, backend inspection and inference share the existing attempt timeout. No attempts, repair, token, context or episode limits were increased. Unknown usage stays conservatively reserved; invalid output with reported usage is still charged. Private notes still have no cloud fallback.

A real development response also supplied an advisory expected-cost integer larger than the checkpoint serializer's 64-bit range. The contract now bounds this non-authoritative field to 100,000,000 cents. A regression drives the malformed HTTP response through rejection, local fallback, PostgreSQL checkpoint, human approval and one ledger commit. Unexpected worker exceptions now produce a safe recoverable `EXECUTION_INTERRUPTED` status; loss of the owning DB session still requires ownership recovery, not silent writes on a replacement connection.

Fast regressions: **92 passed**, covering malformed/missing/duplicate fields, non-string output, truncated usage accounting, oversized advisory integers, unsupported backend, queue timeout, three-city context fit, recovery, persisted quotas/privacy and transactional approval. Fixtures in `tests/test_providers.py` are explicitly mocked HTTP responses; the separate release evaluations use real models. O12 now separately asserts process replacement, fresh authentication, preference version/value restoration, application to a new request and successful valid planning. O09 also requires actual valid completion after reconnection.

### Fresh evaluation reproduction

Do not rerun the fixed-name release orchestrator against the committed outputs. For a new experiment choose a new suffix, copy/edit the orchestration/report input mapping, and preserve all attempted outcomes. After setting up the required evaluation accounts and test controls as described below:

```sh
uv run python -m evaluation.compare_models --output deliverables/evidence/provider-comparison-your-run.jsonl
uv run python -m evaluation.operations --output deliverables/evidence/operations-your-run.jsonl
uv run python -m evaluation.fallback_regression --output deliverables/evidence/fallback-your-run.jsonl
uv run python -m evaluation.run_eval --output deliverables/evidence/benchmark-your-run.jsonl
uv run python -m evaluation.run_attacks --output deliverables/evidence/attacks-your-run.jsonl
```

Run these sequentially, with no browser/demo/other model load in parallel. The current orchestration requires all 36 provider tasks to pass before starting the broader suites, and aborts after any failed operational/outage gate. Each real-run sidecar records source identity and actual backend/model identity. No model keys, account tokens or private environment files belong in evidence. An explicitly interrupted partial attempt remains development evidence, not a completed denominator.

`evaluation.build_followup_report` reads this release's fixed dataset names, verifies exact planning-request equality and the original raw-file hashes against commit `0c4daf9`, then independently audits every emitted proposal and reads actual usage from the local experiment DB. Rebuilding that report requires the experiment database and baseline Git history (`git fetch --unshallow` if needed); the committed report/raw files remain usable without them. It is not a generic report for an arbitrary new suffix. The current local model backend, quantization and contracts changed together; results are an application-release comparison, not a controlled causal model ranking. Two repeats remain a small sample.

## 6. Contribution workflow and checks

Use a small `codex/<task>` branch, describe the problem and acceptance criteria, and open a PR. Preserve the baseline evidence instead of editing it to make an improvement look successful. Coordinate changes to shared graph/schema/persistence contracts with Akshay; do not force-push the shared default branch.

Run checks appropriate to your change. For runtime changes, start with:

```sh
uv run ruff check src scripts evaluation tests
uv run python -m pytest -q
uv run python -m scripts.audit_witnesses
```

For UI changes also run `uv run python -m scripts.browser_check --output deliverables/evidence/ui-your-run` against the local app; it performs real model calls/approval, writes UI evidence and assumes a private `organizer` credential file. Do not overwrite the submitted screenshot set without intentionally preparing a new release. For packaging, `uv run python -m scripts.verify_package --source-only` does not need ffmpeg. The full check uses `ffprobe` and validates the submitted MP4's duration/codec and all five claim ranges.

After source lines or final artifacts change:

```sh
uv run python -m scripts.build_capability_map
uv run python -m scripts.verify_package
uv run python -m scripts.release_manifest
git diff --check
git status --short
```

Review generated changes before committing. The source map resolves actual function symbols/ranges; the release manifest inventories publishable files, excluding itself. The manifest must be regenerated after changing tracked content. The local `dist/TripBudgetAI_Submission.zip` is ignored and is **not automatically rebuilt** by these commands; regenerate it from the final committed files when preparing submission.

CI installs the exact Python patch with `actions/setup-python`, then uses pinned uv and the frozen lock, starts PostgreSQL, migrates, runs Ruff/pytest and verifies the source package. Do not remove the explicit Python bootstrap or pytest repository-root import configuration: earlier clean-machine CI exposed those setup issues. Fixture tests are not substitutes for actual feature/attack evidence.

## 7. Real evaluation: avoid accidental overwrites

Use an isolated database/runtime or a dedicated worktree/clone for a new full experiment. Confirm the server's test controls are enabled only for evaluation, and create the required private evaluation accounts (`benchmark`, `adversary`, `evaluator`, `operations`, `sources`) using `scripts.manage create-user --role evaluation`. Harness credentials are read from `.secrets/<username>.txt`. Evaluation controls are not available to ordinary organizer accounts.

Examples for runners with an output option:

```sh
uv run python -m evaluation.run_eval --output deliverables/evidence/your-new-benchmark.jsonl
uv run python -m evaluation.run_attacks --output deliverables/evidence/your-new-attacks.jsonl
```

Read each runner before executing it:

- `run_eval.py`, `run_attacks.py`, `compare_models.py`, `operations.py` and `fallback_regression.py` accept `--output` and refuse existing raw outputs. Case snapshots are written beside the new dataset. `compare_models --resume` explicitly continues a partial comparison; it is not a fresh rerun. `operations --only O12` is a diagnostic subset, not a replacement for the full 12-case denominator.
- `live_sources.py` retains its historical fixed output path. Use an isolated experiment copy or add an explicit new output option before a fresh source experiment; do not delete submitted evidence.
- `build_report.py` intentionally reads the named final dataset files and asserts the original 154-unit counts. A new experiment needs separately versioned inputs/report logic; do not silently combine it with the baseline.
- Operational tests start separate local servers and deliberately terminate a serving process / owning DB session. Use development infrastructure, not an active shared demo/cloud database.
- Local ports: app **8084**, optional cloud proxy **8085**, attack worker **8086**, mutated-catalog worker **8087**, operations **8088**, recording **8089**, PostgreSQL **55434**, temporary Cloud SQL proxy **55435**, Ollama **11435**. Check for collisions rather than killing unrelated processes.

Scenario generators choose a start date relative to the day of execution. A later-date experiment needs its own dated snapshots; preserve original requests, and label any date changes explicitly. Historical requests or source facts can expire and must not be made acceptable by disabling freshness checks.

Freeze inputs, rubric/scorer, catalog and source version before a measured comparison. Save every failure, provider usage/unknown reservation, exposure distinction and attempted denominator. Do not rerun only failed cases until they pass and replace the original record.

## 8. Cloud deployment and operations context

**1.0.1 rollout status:** deployed and verified after explicit owner authorization. Revision **`a4-tripbudget-00003-jh7`** serves 100% of traffic with IAM-private invocation. Actual Cloud Run/Cloud SQL planning → human approval → ledger commit passed; absent-laptop private notes returned 503 and anonymous invocation returned 404. The linux/amd64 source/lock hashes match the evaluated application. Uploaded image index `sha256:8dcebc069df573d48df653a53afe1aaa906145ba8eddd8e049825c024af4468e` resolves to deployed platform digest `sha256:d29c2419243f11bc10d9f42ee4f8c841fe5fd38f392a59f0aa89b4911ba4820e`; their link was checked against the registry manifest. Evidence: `deliverables/evidence/cloud-release-v101.json`, `cloud-smoke-v101.json`, `container-image-v101.json`, `container-index-v101.json` and `deployment-status-v101.json`. No schema migration or A3 resource/network changes were needed.

The deployed resources are Akshay's dedicated A4 resources in project **`csci599-a3-hermes-1029`**, region **`us-central1`**. That project also contains earlier work; do not modify or delete unrelated resources.

- Cloud Run service / SQL instance / Artifact Registry repository: **`a4-tripbudget`**. Current verified revision: **`a4-tripbudget-00003-jh7`**; check current live state before operating. The historical 1.0.0 revision was `a4-tripbudget-00002-7tg`. Current digest/readiness are in `deliverables/evidence/cloud-release-v101.json`; historical details remain in `cloud-release-revision.json`. Tags can move: use a new version tag and deploy/record its resolved digest for future releases.
- Standard Cloud Run service: 2 vCPU / 2 GiB, concurrency 8, min 0 / max 2 instances, timeout 300s. PostgreSQL16 micro is zonal with 10 GB storage and daily backups; it is not an HA/SLA production database.
- Runtime SQL user is DML-only; migrations use an operator account. Dedicated secrets are `a4-tripbudget-db`, `a4-tripbudget-nvidia` and `a4-tripbudget-tavily`, accessible to the dedicated serving service account.
- Invocation is **IAM restricted**, in addition to application login. Automatic approval review rejected public unauthenticated ingress; the private alternative was deployed and verified. Do not add public access as a setup shortcut.
- The cloud release supports public-to-provider planning, durable approval and ledger commit. **No cloud-to-laptop bridge is configured.** Private notes fail closed there; the full hybrid demonstration runs locally. No A3 Tailscale grant was broadened. Firebase verification is optional source support, not a verified deployed identity integration.
- `scripts/provision_cloud.py`, `push_image.py` and `cloud_smoke.py` contain owner-specific resource defaults. **Do not run them unchanged against shared resources.** The provisioning helper is one-time initialization, not a safe general rerun/rotation tool. Read `infra/README.md` and obtain owner authorization/access before changes.

With authorized IAM access, the standard local proxy recipe is:

```sh
gcloud run services proxy a4-tripbudget --region us-central1 --project csci599-a3-hermes-1029 --port 8085
```

The optional proxy component may need installation. The cloud smoke script demonstrates a short-lived IAM `X-Serverless-Authorization` header alongside a separate application `Authorization` session. Never commit or display either token. Creating a fresh local database requires no access to Akshay's cloud secrets or copied CLI credential cache.

The report estimates gross deployment at **$2.52/week**, and **$5.54/week** with its stated model/search/electricity allowances; actual billing was unavailable. SQL/storage remain billable even when Cloud Run scales to zero. Monitoring signals are specified, but external alert delivery and backup restoration drills are not verified. Resource deletion/shutdown is an owner decision, not an automatic contributor cleanup step.

## 9. Known limits and useful next contributions

Agree on one bounded task and preserve the safety/measurement contracts above:

| Priority / task | Why | Acceptance criteria |
|---|---|---|
| Submission review and teammate accountability | The process log is still a review draft; Spaces access and Brightspace upload are not certified | Each actual team member reviews their contribution/understanding and writes their own 200–300-word log; owner verifies grader access and submission receipt |
| Provider monitoring / broader holdout | 1.0.1 fixes the recorded provider and O12 failures; finite reruns do not guarantee provider availability | Keep failure/usage traces, extend independently specified holdouts and load tests; retain explicit bounded failure when both providers are down |
| Source availability/freshness | One direct fetch failed; only five reviewed price facts; source snapshots expire | Review new source spans, maintain estimate labels, recompute manifest/index and require new approval when authoritative evidence changes |
| Optional cloud/laptop bridge | Cloud private-note processing is intentionally unavailable | Owner-approved network/identity scope; real cloud↔local test, outage/privacy tests and updated demonstration; no reuse/broadening of A3 grants by assumption |
| Additional deployment hardening | Demo tier and residual trust risks are documented | Transport DNS pinning, stronger identity/RLS, HA/restore/load tests as a scoped project; describe precisely what was actually verified |

Other limitations: no global-optimum claim for bounded eight-variant repair search; no universal injection-resistance guarantee; residual DNS validation-to-connection gap and provider/publisher/session trust; no real ticket inventory, precise accessible-route or restaurant suitability guarantee. Application quotas are not an internet-scale WAF. Expired/changed evidence must cause refresh/replanning, not bypassing digest/expiry checks.

## 10. Submission artifacts and assignment constraints

| Deliverable | Where / status |
|---|---|
| Source + setup/deployment + five-field code map | Repository and README; exact source references in `docs/capability-map.json` |
| Actual 5–10 minute MP4 | `deliverables/video/TripBudgetAI_Demo.mp4`: **7:05**, H.264/AAC, actual runtime with captions and labeled synthesized narration |
| Feature/video evidence | `docs/recording-evidence.md`, `recording-claims.json`, `deliverables/evidence/recorded-run.json`; recorded episode `268c5558d33f4d81ab6d31e5b70911c8` |
| Technical presentation | `deliverables/TripBudgetAI_Technical_Presentation.pdf`: **16 slides**; editable Spaces reference and topic inventory in `deliverables/TECHNICAL_PRESENTATION.md` |
| Quantitative report | Current `deliverables/EVALUATION_FOLLOWUP_1.0.1.md` / `metrics-v101.json`; historical `EVALUATION_REPORT.md` / `metrics.json`; both sets of raw traces and per-session usage |
| Individual process log | `PROCESS_LOG.md`: **258-word review draft for Akshay**; not the teammate's log and not certification of personal understanding |
| Portable source/artifact ZIP | Locally generated, ignored `dist/TripBudgetAI_Submission.zip`; rebuild after contribution changes |

The newer handout allows at most two students, requires at least three advanced features actually triggered in the video, at least three **real** prompt-injection attacks with actual traces/mitigations, and at least ten slides covering architecture/design, capabilities/limits, safety, metrics and future work. The report must include measured sample/date, failures, tokens/session and numerical weekly cost. Enforceable guardrails must exist outside prompts. Every team member needs an individual 200–300-word log covering AI tools, development, attribution, verification and learning. Two-person scope should reflect actual contributions.

The video and slide PDF are explicitly **historical 1.0.0** artifacts: they demonstrate all five features, but their recorded metrics/backend are not the new 1.0.1 results. Read the labeled follow-up for current results. Current five-feature claims remain implemented. If you change/remove a feature, update the README map, video, slides, report and claim timestamps consistently. Do not claim A2A, public app uptime, Firebase deployment, alert delivery or the laptop bridge merely because a configuration/interface exists. No live application URL is required for grading; grader access to any restricted Spaces artifact still needs to be granted or the portable artifacts uploaded.

This is original Assignment 4 application code, not an A3 continuation. Codex assistance is disclosed in the process log. Library imports are distinct from adapted external code; substantial external adaptations need source comments and process-log attribution per the handout. Preserve truthful attribution and do not reuse the owner's reflection as another student's personal log.

## 11. Troubleshooting and first contribution checklist

- **Database connection refused:** start Docker/compose; check `docker compose ps`, port 55434 and matching password/DSN. Changing `.env` does not rotate a password already stored in the database volume. Do not delete a shared volume to resolve a login issue.
- **Missing schema:** run the explicit migration against your intended development database. Serving workers do not migrate automatically.
- **`CORPUS_NOT_READY`:** build the actual index with `Corpus(Settings()).build()`. **`DATA_GAP` on stale facts:** inspect the dates and versioned facts; do not disable expiry or silently call an estimate verified.
- **`LOCAL_UNAVAILABLE`:** check the intended loopback Ollama server, model alias and capacity. Private notes must not be routed to cloud to hide the error.
- **`PROVIDER_UNAVAILABLE` / context or rate limit:** inspect durable model failure/usage events; use bounded explicit recovery. Do not increase attempts or erase counters to make a measured run pass.
- **`RUN_BUSY`:** another owner-scoped worker holds the database session lock. Let it finish/recover; do not bypass ownership.
- **409 on approval/preference:** inspect stale revision/hash/expiry or preference version and reload; create a fresh plan/decision when needed. Never edit an immutable proposal row as a workaround.
- **Harness refuses a path:** pick a new `--output`; never remove committed evidence. For a deliberate partial comparison continuation use `--resume` and label it as such.
- **`LOCAL_BACKEND_UNSUPPORTED`:** inspect `/api/show` locally; use the pinned GGUF alias, not an MLX alias.
- **`EXECUTION_INTERRUPTED`:** inspect the episode trace for the safe exception category, correct the underlying issue, then retry using checkpoint recovery and existing counters.

Before opening a PR: establish access and a separate branch; reproduce the baseline appropriate to your task; state acceptance checks; change the smallest relevant modules; preserve frozen evidence; update source map/report/video only when affected; regenerate the inventory; confirm no secrets/runtime state are staged; let CI pass; document actual contribution and any remaining limits. Ask Akshay to review cloud/resource or grading-claim changes before merging them into the shared release.
