# Threat model and enforced boundaries

Protected assets: per-organizer preferences, trip constraints, approved proposal content, the single ledger, authentication credentials, private note text and bounded provider spend. Untrusted surfaces: request prose, imported synthetic notes, retrieved guide chunks, search/MCP results and every LLM response. The organizer is allowed to choose constraints and confirm structured preferences; a document/model has no such authority.

| Surface / failure | Enforceable boundary | Residual limitation |
|---|---|---|
| Instruction in request/guide says raise cap | Caps originate in strict TripRequest; reconstruction computes and checks per-person and group totals | Model may verbally repeat an attack; advisory text is displayed as untrusted observations |
| Fake price or omitted tax/room | Selected IDs resolve to reviewed catalog or confirmed all-in estimate; room count, every meal/night, transfer and buffer are rebuilt | A confirmed estimate can still be wrong in the real world |
| Forged approval | Separate authenticated HTTP decision; owner/hash/revision/expiry; transaction and uniqueness | A compromised human session can exercise that human's authority |
| Persistent preference poisoning | Model returns only typed fields; an explicit confirmation endpoint performs versioned writes; no arbitrary memory blob | A user could confirm a harmful or unwanted value within allowed bounds |
| Private-note exfiltration | Local-only provider route and one-attempt policy; no cloud fallback, search or raw-note persistence | Trusts the configured local endpoint; use synthetic notes only |
| SSRF/recipient/code request | Agent has no mail, shell, booking, payment or browser tool; source host allowlist, HTTPS, public IPs, no redirects | DNS rebinding between validation and connection remains; transport-level pinned DNS is future work |
| Cross-user read/write | Owner predicates on episode, event, approval, preferences and ledger endpoints; hashed sessions | Runtime database account has app-wide DML access; database RLS is not claimed |
| Duplicate worker/commit | PostgreSQL session advisory ownership, serialized official checkpoint/business operations, row locks and unique episode/revision ledger | Session loss aborts work; recovery can require an explicit retry |
| Runaway iteration/spend | Persisted reservations/counters; 24 logical calls, 32 attempts, two repairs, active deadline, tool quotas and daily admission caps | Unknown provider charges cannot be measured precisely; conservative reservation is retained |
| Browser content injection | DOM textContent, strict same-origin CSP, no inline scripts/eval, no third-party assets | SessionStorage bearer token is exposed to same-origin script compromise; enterprise cookie/OIDC hardening deferred |

Local-mode authentication uses Argon2 passwords and durable hashed sessions. Firebase server-side ID-token verification is an implemented optional adapter, not a tested/claimed deployed identity integration. Cloud Run additionally requires IAM invocation. Test controls require an evaluation/admin role and a server setting; ordinary organizers cannot activate simulated faults.

Read the evaluation report for the actual ten attack payloads, injected surfaces, model exposure, observed traces, utility and mitigation. Synthetic attack inputs were submitted to the operating app and real retrieval adapters; responses were not fabricated. Zero observed unauthorized protected-state changes in a small sample is not a universal security proof. Prompt instructions supplement these code/architecture boundaries but are not counted as guardrails.
