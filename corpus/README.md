# Evidence corpus

`catalog.json` contains a dated planning snapshot: 24 official source records, 12 scoped activities, explicit routes, 68 original summary chunks and provenance. `manifest.json` binds the catalog SHA-256. Raw downloaded pages are ignored and not redistributed. Short reviewed price spans are stored with source digests; no LLM output can promote a discovered amount into a verified fact.

`seed.py` defines the source registry and original summaries; `scripts.build_corpus` captures sources and writes a new digest/version; `scripts.review_facts` applies narrow source-span review rules. The frozen release has five reviewed numerical price facts. Operating windows, walk/transfer durations, lodging, meals, local transit and intercity fares remain explicit estimates even if an official page was fetched. The organizer must confirm their use. Unavailable source pages do not imply verified claims.

`data/chroma` and BGE weights are reproducible derived runtime assets and excluded from Git. `Corpus.build()` creates the real dense index from the committed original summaries. The attack harness uses the same adapter to index an additional untrusted guide chunk in an isolated collection; it never overwrites reviewed catalog prices.

Refreshes are operator actions, not model tool capabilities. Review the changed facts and manifest, rebuild the index, and require a new approval whenever authoritative evidence changes. Expired snapshots fail closed. Corpus breadth is intentionally 68 substantive chunks rather than padding to the plan's 80–160 estimate.
