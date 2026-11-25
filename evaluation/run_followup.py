"""Run the affected real suites sequentially, preserving every baseline dataset."""

import json
import subprocess
import sys
from pathlib import Path


def main():
    folder = Path("deliverables/evidence")
    providers = folder / "provider-comparison-v101.jsonl"
    results = [json.loads(s) for s in providers.read_text().splitlines()]
    if len(results) != 36 or not all(r["success"] for r in results):
        raise SystemExit(
            "Provider gate: require a complete successful real comparison before the wider release run"
        )
    stages = [
        ("operations", "evaluation.operations", "operations-v101.jsonl"),
        ("fallback", "evaluation.fallback_regression", "fallback-v101.jsonl"),
        ("benchmark", "evaluation.run_eval", "benchmark-v101.jsonl"),
        ("attacks", "evaluation.run_attacks", "attacks-v101.jsonl"),
    ]
    for stage, module, name in stages:
        target = folder / name
        if target.exists():
            raise SystemExit("Refusing to overwrite " + str(target))
        print("Starting", stage, flush=True)
        with Path(".runtime/logs/" + stage + "-v101.log").open("w") as log:
            subprocess.run(
                [sys.executable, "-m", module, "--output", str(target)], check=True, stdout=log, stderr=log
            )
        print("Completed", stage, flush=True)
        if stage in {"operations", "fallback"}:
            measured = [json.loads(line) for line in target.read_text().splitlines()]
            if not all(row["success"] for row in measured):
                raise SystemExit("Release gate failed: " + stage + "; raw failures preserved")


if __name__ == "__main__":
    main()
