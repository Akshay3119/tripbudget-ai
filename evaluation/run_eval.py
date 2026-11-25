import argparse
import asyncio
import hashlib
import json
import os
import random
import signal
import sys
import time
from datetime import timedelta
from pathlib import Path

import httpx

from .client import AppClient
from .scenarios import scenarios
from tripbudget.schemas import utcnow


def mutated_catalog(mutation, target):
    data = json.loads(Path("corpus/catalog.json").read_text())
    if mutation == "missing_fare":
        data["routes"]["NYC-PHL"]["price_cents"] = None
    elif mutation == "missing_route":
        del data["routes"]["NYC-PHL"]
    elif mutation == "expired_activity":
        data["activities"][0]["expires_at"] = (utcnow() - timedelta(days=1)).isoformat()
    target.mkdir(parents=True, exist_ok=True)
    path = target / "catalog.json"
    path.write_text(json.dumps(data, indent=2))
    manifest = json.loads(Path("corpus/manifest.json").read_text())
    manifest["catalog_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2))


async def wait_ready(url, process):
    async with httpx.AsyncClient(trust_env=False, timeout=2) as client:
        for _ in range(100):
            if process.returncode is not None:
                raise RuntimeError("Evaluation runtime exited before readiness")
            try:
                response = await client.get(url + "/readyz")
                if response.status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.2)
    raise RuntimeError("Evaluation runtime readiness timed out")


async def execute(client, case, condition, repeat):
    started = time.monotonic()
    record = {
        "case": case["id"],
        "kind": case["kind"],
        "condition": condition,
        "repeat": repeat,
        "at": utcnow().isoformat(),
        "request": case["request"],
    }
    try:
        admission = await client.post("/api/episodes", case["request"])
        identifier = admission["id"]
        record["episode"] = identifier
        result = await client.run(identifier, repair_enabled=condition == "corrected")
        record["state"] = result["state"]
        record["frames"] = result["frames"]
        status = result["state"]["status"]
        record["outcome"] = status
        if case["kind"] == "feasible":
            record["success"] = status == "PENDING_APPROVAL" and result["state"]["proposal"]["valid"]
        elif case["kind"] == "infeasible":
            record["success"] = status == "PROVEN_INFEASIBLE"
        else:
            record["success"] = status in {"DATA_GAP", "NEEDS_INPUT", "INPUT_VALIDATION"}
        record["unsafe_commit"] = result["state"]["ledger_id"] is not None
    except httpx.HTTPStatusError as exc:
        body = exc.response.json()
        record["outcome"] = body.get("error", str(exc.response.status_code))
        record["success"] = case["kind"] == "incomplete" and exc.response.status_code == 422
        record["response"] = body
    record["elapsed_seconds"] = round(time.monotonic() - started, 3)
    return record


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--only", default="")
    parser.add_argument("--output", default="deliverables/evidence/benchmark.jsonl")
    args = parser.parse_args()
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        raise SystemExit("Refusing to overwrite raw evaluation evidence; choose another output")
    cases = scenarios()
    out.with_suffix(".cases.json").write_text(json.dumps(cases, indent=2))
    client = await AppClient(username="benchmark").login()
    from .metadata import release_metadata
    from tripbudget.settings import Settings

    metadata = await release_metadata(client, Settings())
    out.with_suffix(".metadata.json").write_text(
        json.dumps(
            {
                "at": utcnow().isoformat(),
                "release": metadata,
                "source_manifest": json.loads(Path("corpus/manifest.json").read_text()),
                "repeats": args.repeats,
                "method": "paired ablation; same input, evidence, model policy and safety; randomized condition order",
            },
            indent=2,
        )
    )
    rng = random.Random(599)
    try:
        for case in cases:
            if args.only and case["id"] not in args.only.split(","):
                continue
            special = None
            selected = client
            log = None
            if case.get("mutation") in {"missing_fare", "missing_route", "expired_activity"}:
                folder = Path(".runtime/eval-catalogs") / case["id"]
                mutated_catalog(case["mutation"], folder)
                env = dict(os.environ, TRIPBUDGET_CORPUS_DIR=str(folder.resolve()))
                log = await asyncio.to_thread(open, f".runtime/logs/eval-{case['id']}.log", "w")
                special = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "tripbudget.api:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8087",
                    "--no-access-log",
                    env=env,
                    stdout=log,
                    stderr=log,
                )
                await wait_ready("http://127.0.0.1:8087", special)
                selected = await AppClient("http://127.0.0.1:8087", username="benchmark").login()
            try:
                for repeat in range(args.repeats):
                    conditions = ["baseline", "corrected"]
                    rng.shuffle(conditions)
                    for condition in conditions:
                        record = await execute(selected, case, condition, repeat + 1)
                        await asyncio.to_thread(append_record, out, record)
                        print(
                            case["id"],
                            condition,
                            repeat + 1,
                            record["outcome"],
                            record["success"],
                            record["elapsed_seconds"],
                            flush=True,
                        )
            finally:
                if special:
                    await selected.close()
                    special.send_signal(signal.SIGTERM)
                    try:
                        await asyncio.wait_for(special.wait(), timeout=10)
                    except TimeoutError:
                        special.kill()
                        await special.wait()
                    log.close()
    finally:
        await client.close()


def append_record(path, record):
    with path.open("a") as file:
        file.write(json.dumps(record) + "\n")


if __name__ == "__main__":
    asyncio.run(main())
