# Originality and design decisions

This is a fresh application for the Assignment 4 capstone. The work starts from a travel-specific constraint model, cost ledger and evidence catalog, not from the Assignment 3 personal-assistant domain, router or tool set. Runtime credentials and a local Ollama executable were reused as environment resources; no previous assistant application source or user data was imported. Public embedding weights are standard dependency assets, not prior assignment implementation.

The supervisor and three specialist nodes provide actual model-supported planning/inspection, but specialist prose is deliberately advisory. Deterministic code is the authority for cost and timing. A constrained repair menu is a read-only tool result: it enumerates eight tier/cadence/free-vs-all combinations, validates each, and returns up to three. The model selects a candidate and explains the change. This is bounded tool-aided search, not a global optimum claim. A valid initial plan needs no repair; an invalid baseline is retained as a failed case. Two repair passes cannot guarantee feasibility discovery.

Why these components:

- PostgreSQL keeps approval authority, preferences, counters, events and official LangGraph checkpoints across process replacement. One invocation session owns advisory locks and checkpoint writes. Losing that session releases ownership; work cannot safely continue on a silently reconnected lock-free session.
- Immutable proposals and hash-bound decisions separate suggestion from authority. Approval is not parsed out of a model answer. A transaction reconstructs an approved proposal from the current request/catalog and enforces exactly one ledger per revision.
- Integer cents and rational largest-remainder allocation handle indivisible cents without float drift. Odd group sizes round room count upward. Individual caps remain binding even when the group aggregate fits.
- A versioned catalog distinguishes reviewed price snapshots from explicit estimates. Embedding similarity is useful for discovery, not sufficient evidence of a price. Retrieved instructions cannot alter catalog numbers.
- Query coverage grading is a deterministic price+schedule check; an actual LLM rewrites deficient public queries and Chroma is queried again. This is iterative RAG, not a claim that an LLM can certify source truth.
- A policy router sends public multistep reasoning to NVIDIA NIM and short utility/private-note work to local Gemma E4B. Public tasks permit at most one alternate-provider attempt. Restricted notes cannot fall back externally.
- A standard Cloud Run service fits a bounded HTTP workflow with explicit resume. The full hybrid local demo and IAM-restricted cloud-only deployment are separate, labeled runtime modes. PostgreSQL, rather than container memory/files, is the durable authority in both.

No external tutorial application code was copied. Framework/library APIs are used through ordinary imports. `docs/IMPLEMENTATION_LOG.md` records development failures and corrections. Runtime evidence, report and process-log disclosure describe AI-assisted generation and verification. Personal understanding and the final individual reflection remain the student's responsibility.
