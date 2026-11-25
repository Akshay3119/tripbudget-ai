# Implementation record

All entries describe actual work, not planned test outcomes. Runtime evidence is stored separately.

## November 25, 2026 — initial vertical slice

- Created a fresh application; no Assignment 3 source files were imported or copied.
- Resolved and locked 157 Python packages. PostgreSQL 16 runs in an isolated Docker volume on loopback 55434.
- Verified actual NVIDIA Lightning completion and official `AsyncPostgresSaver` setup.
- Started a separate Ollama server on loopback 11435 and downloaded Gemma 4 E4B. Built the project alias with 8,192 context.
- Fetched 24 official source records: 20 succeeded, four remained explicitly unavailable. Built a real BGE/Chroma index with 68 original-summary/source-policy chunks. Reviewed five admission/fare price fields against brief exact official-source spans; other amounts/windows remain explicit planning estimates.
- First integration failure: psycopg prepared statements do not accept the multi-command migration string; corrected operator migration execution.
- Second integration failure: a nested store operation opened another connection inside an uncommitted admission transaction; propagated the transaction connection through request/task context.
- Third integration failure: checkpointer pipeline writes raced application SQL on the same session. Added a shared reentrant operation lock used by the official saver and business transactions. Added a concurrent pipeline/business-transaction regression test.
- First actual multi-agent run safely rejected an over-budget proposal but repeated a poor LLM repair estimate. Preserved the unsuccessful run. Added independently priced feasible repair alternatives as a read-only tool observation for the agent to select.
- Subsequent actual run corrected USD 1,056/person to USD 770/person, paused durably for human approval, and saved one ledger after an authenticated decision. See the dated smoke evidence.
- Initial 44 tests passed; expanded finance/policy/PostgreSQL suite reached 48 passing tests.
- Actual Chromium desktop sign-in → planning → approval → ledger flow passed with no JavaScript errors; mobile 390px layout had no horizontal overflow. The first browser harness used a CSP-incompatible polling API; changed the test assertions, preserving the application's strict CSP.

## Release work still in progress

The benchmark, deployed/local operating-system attack traces, operational restart tests, source map, final evaluation report, slides, MP4, package/security audit and GitHub push are release gates. None is claimed complete by this log until its actual result is recorded.

## Final real evaluation and submission evidence — 2026-11-25

- Frozen final suites completed 154 logical units: 80 paired planning runs, 20 real attack episodes, 36 matched provider tasks, 12 operating/fault cases and six live-source checks.
- Corrected feasible completion: 22/24; baseline4/24. All18 runs that reached an initially invalid corrected critic result repaired successfully. Two feasible runs failed at a provider step; retained in raw evidence and report.
- Independent oracle audits26/26 emitted proposals and all12 feasible witness plans. Expanded regression suite70/70 passed, including odd group sizes, missing mandatory costs and manifest tampering.
- All20 attacks preserved observable protected state;13 actually exposed the payload to a model and19 completed the legitimate task. Unexposed guide attempts are not described as model resistance.
- Actual operating faults11/12 passed. O12 restored confirmed preferences, then planning returned PROVIDER_UNAVAILABLE; the full failure remains scored false. A read-only DB inspection preserves the restored values and memory event separately.
- Three actual Tavily MCP searches succeeded after removing an unsupported parameter; one of three direct publisher fetches still failed and remains unavailable.
- Dedicated IAM-private Cloud Run and Cloud SQL deployment completed an actual plan/approval/ledger flow. The first smoke used an overly narrow403-only anonymous-denial assertion; Cloud Run masks its private route as404. The original completed flow/assertion failure is retained and the corrected verification also succeeded. Public unauthenticated deployment was rejected by automatic approval review; the private alternative was used.
- Recording automation was corrected to open expandable controls and reconfirm estimate consent after the demonstrated process replacement. Failed recording takes are ignored development media, not fabricated success evidence.
- Final UI regression clears a previous itinerary/approval when submitting a new infeasible request. This is a presentation-state fix after the core evaluation, with a separate actual browser regression; it does not change planning benchmark behavior.
- Sixteen native editable slides were rendered and visually reviewed. The portable PDF is a snapshot of those reviewed renders; editable source remains in Spaces. No PowerPoint-app compatibility check is claimed.

- Final verification adds an admission replay regression after saved preferences normalize an active request:71/71 automated tests pass. Actual final MP4 is425 seconds, H.264/AAC,7.2MB, successfully seeks/plays in Chromium; mean audio-19.4dB/max-1.5dB. Final UI browser flow passes with zero JS errors and explicit clearing of old results after an infeasible new request.
