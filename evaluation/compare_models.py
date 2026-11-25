"""Matched public task comparison. Uses real endpoints and measured token usage; no private notes."""

import asyncio
import argparse
import json
import random
import time
from pathlib import Path

from tripbudget.evidence import Catalog
from tripbudget.persistence import Store, digest
from tripbudget.providers import Providers
from tripbudget.resources import Budget
from tripbudget.schemas import ModelPreferences, QueryRewrite, plan_choice_schema, utcnow
from tripbudget.settings import Settings

from .client import AppClient, default_request
from .run_eval import append_record


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="deliverables/evidence/provider-comparison-new.jsonl")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and not args.resume:
        raise SystemExit("Refusing to overwrite evidence; --resume skips only recorded keys")
    completed = (
        {
            (r["id"], r["provider"], r["repeat"])
            for r in [json.loads(line) for line in out.read_text().splitlines()]
        }
        if out.exists()
        else set()
    )
    settings = Settings()
    store, providers, catalog = (
        Store(settings),
        Providers(settings),
        Catalog(settings.corpus_dir / "catalog.json"),
    )
    client = await AppClient(username="evaluator").login()
    identity = await client.get("/api/meta")
    from .metadata import release_metadata

    if not args.resume:
        out.with_suffix(".metadata.json").write_text(
            json.dumps(await release_metadata(client, settings), indent=2)
        )
    cases = []
    for city in ["NYC", "PHL", "DC"]:
        ids = [x["id"] for x in catalog.activities.values() if x["city"] == city]
        cases.append(
            (
                "select-" + city,
                "supervisor",
                plan_choice_schema([city], catalog.compact([city], utcnow())),
                {
                    "instruction": "Select economy lodging, one activity per day, and include all supplied IDs under the exact city code.",
                    "constraints": {"cities": [city]},
                    "catalog": catalog.compact([city], utcnow()),
                },
                {"city": city, "ids": ids},
            )
        )
        cases.append(
            (
                "query-" + city,
                "query_rewrite",
                QueryRewrite,
                {
                    "instruction": "Rewrite a public query for admission prices and opening hours. Include city code.",
                    "city": city,
                    "query": city + " group cultural activities",
                },
                {"city": city},
            )
        )
    for i, (diet, walk) in enumerate([("vegan", 4000), ("vegetarian", 6000), ("unrestricted", 12000)]):
        cases.append(
            (
                f"preferences-{i + 1}",
                "preference_parse",
                ModelPreferences,
                {
                    "instruction": "Extract diet and walking limit. This is public synthetic evaluation input.",
                    "untrusted_note": f"We prefer {diet} food and a maximum of {walk} meters walking daily.",
                },
                {"diet": diet, "maximum_walk_meters": walk},
            )
        )
    out.with_suffix(".cases.json").write_text(
        json.dumps(
            [
                {"id": i, "task": t, "schema": s.model_json_schema(), "payload": p, "oracle": o}
                for i, t, s, p, o in cases
            ],
            indent=2,
        )
    )
    rng = random.Random(599)
    try:
        for identifier, task, schema, payload, oracle in cases:
            for repeat in [1, 2]:
                order = ["local", "cloud"]
                rng.shuffle(order)
                for provider in order:
                    if (identifier, provider, repeat) in completed:
                        continue
                    episode = (await client.post("/api/episodes", default_request(days=3, cities=["NYC"])))[
                        "id"
                    ]
                    record = {
                        "id": identifier,
                        "task": task,
                        "provider": provider,
                        "repeat": repeat,
                        "at": utcnow().isoformat(),
                        "episode": episode,
                        "payload_hash": digest(payload),
                        "oracle": oracle,
                        "actual_execution": True,
                    }
                    start = time.monotonic()
                    try:
                        result = await providers.complete(
                            task, schema, payload, Budget(store, episode, identity["uid"]), force=provider
                        )
                        value = result.model_dump()
                        record["response"] = value
                        if task == "supervisor":
                            passed = (
                                value["lodging_tier"] == "economy"
                                and value["activities_per_day"] == 1
                                and set(value["activities"]) == {oracle["city"]}
                                and set(value["activities"][oracle["city"]]) == set(oracle["ids"])
                            )
                        elif task == "query_rewrite":
                            passed = (
                                oracle["city"].lower() in value["query"].lower()
                                and any(x in value["query"].lower() for x in ["admission", "price", "cost"])
                                and any(x in value["query"].lower() for x in ["hours", "opening", "schedule"])
                            )
                        else:
                            passed = all(value[k] == v for k, v in oracle.items())
                        record["success"] = passed
                    except Exception as exc:
                        record.update(success=False, error=getattr(exc, "code", type(exc).__name__))
                    record["elapsed_seconds"] = round(time.monotonic() - start, 3)
                    record["usage"] = await store.all(
                        "SELECT provider,model,input_tokens,output_tokens,reasoning_tokens,reserved,success,error FROM model_usage WHERE episode=%s",
                        (episode,),
                    )
                    append_record(out, record)
                    print(identifier, provider, repeat, record["success"], flush=True)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
