# Recording evidence

This is actual historical release 1.0.0 footage. Release 1.0.1 changes the model backend/structured-output adapter; its current real-run and restart/fallback evidence is in the [follow-up report](../deliverables/EVALUATION_FOLLOWUP_1.0.1.md). The five application capabilities and authority boundaries remain implemented.

[Actual MP4](../deliverables/video/TripBudgetAI_Demo.mp4). Duration approximately7:05, H.264/AAC. The browser/OS/model actions are actual runtime captures. Captions and synthesized narration annotate them; no model/tool response is substituted. Idle time is retained.

Recorded planning episode: `268c5558d33f4d81ab6d31e5b70911c8`. Raw [recorded run](../deliverables/evidence/recorded-run.json), [timed captions/boot IDs](../deliverables/video/recording-events.json).

| Claimed feature | MP4 range | Observed behavior |
|---|---|---|
| Long-term memory | 1:05–4:15 | Confirmed preference saved; actual new boot + fresh login restores vegetarian/6000m values |
| Planning and self-correction | 1:35–3:15 | Actual model proposal, failed cost critic, repair selection and successful recheck |
| Durable human-in-the-loop | 2:50–4:45 | Hash-bound pending approval survives actual process replacement; human approval commits one ledger |
| Iterative RAG/source verification | 1:35–5:20 | Real retrieval/query rewrite events and evidence library; estimates visibly separate |
| Hybrid cloud/local inference | 0:25–2:50 | Actual local-only note extraction and local query rewrite, cloud model selection/completions |

Guardrail segment5:20–6:35: a new $50/person request cannot cover mandatory meals and includes an instruction to bypass approval; code returns PROVEN_INFEASIBLE without certifying/committing a new plan. That proof is an engaged numerical guardrail, not counted as a model-exposed injection test. Ten separate real attack types are documented in the evaluation report.

Actual OS process termination at 195.13s. Boot identity changes from `Release 1.0.0 · local · boot f3ee2c638f01e9b9` to `Release 1.0.0 · local · boot f08ca02ec7e0005e`; saved values reload after fresh login. Human approval commits at 255.91s. The exact cost changes and real usage rows are in the linked trace.

The recording predates the final UI cleanup that clears the prior itinerary immediately on a new infeasible submission. Core planning/approval/guardrail behavior is the same; the final actual browser regression also verifies that presentation-state cleanup. No cloud-to-laptop bridge, A2A protocol or live booking capability is claimed.

Local MP4 playback, decodability, duration, audio and representative frames are checked before publication. Private repository/artifact access must be granted to graders; no Brightspace upload is claimed.
