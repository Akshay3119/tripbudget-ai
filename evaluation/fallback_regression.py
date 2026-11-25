"""Real local inference under a labeled cloud-429 fault; no mocked provider responses."""

import argparse
import asyncio
import json
import time
from pathlib import Path

from tripbudget.schemas import utcnow
from tripbudget.settings import Settings
from .client import AppClient
from .metadata import release_metadata
from .oracle import audit
from .run_eval import append_record
from .scenarios import scenarios


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    out = Path(args.output)
    if out.exists():
        raise SystemExit("Refusing to overwrite fault evidence")
    client = await AppClient(username="evaluator").login()
    out.with_suffix(".metadata.json").write_text(
        json.dumps(await release_metadata(client, Settings()), indent=2)
    )
    catalog = json.loads(Path("corpus/catalog.json").read_text())
    try:
        for case in [c for c in scenarios() if c["id"] in {"F01", "F03", "F08"}]:
            start = time.monotonic()
            episode = (await client.post("/api/episodes", case["request"]))["id"]
            result = await client.run(episode, simulate_cloud_429=True)
            trace = [f["data"] for f in result["frames"] if f["event"] == "trace"]
            errors = (
                audit(case["request"], result["state"]["proposal"], catalog)
                if result["state"]["proposal"]
                else ["no_proposal"]
            )
            record = {
                "case": case["id"],
                "at": utcnow().isoformat(),
                "episode": episode,
                "request": case["request"],
                "fault": "authenticated simulated cloud429; actual local GGUF inference",
                "run": result,
                "independent_audit_errors": errors,
                "elapsed_seconds": round(time.monotonic() - start, 3),
            }
            record["success"] = (
                result["state"]["status"] == "PENDING_APPROVAL"
                and not errors
                and any(
                    e["kind"] == "model_failure" and e["data"].get("error") == "CLOUD_429_SIMULATED"
                    for e in trace
                )
                and any(
                    e["kind"] == "model_result"
                    and e["data"].get("provider") == "local"
                    and e["data"].get("local_backend", {}).get("format") == "gguf"
                    for e in trace
                )
            )
            append_record(out, record)
            print(
                case["id"],
                record["success"],
                result["state"]["status"],
                record["elapsed_seconds"],
                flush=True,
            )
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
