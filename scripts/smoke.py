import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation.client import AppClient, default_request  # noqa: E402
from tripbudget.schemas import utcnow  # noqa: E402


async def main():
    client = await AppClient().login()
    started = time.monotonic()
    episode = await client.post("/api/episodes", default_request())
    result = await client.run(episode["id"])
    state = result["state"]
    directory = Path("deliverables/evidence")
    directory.mkdir(parents=True, exist_ok=True)
    file = directory / ("smoke-" + utcnow().strftime("%Y%m%dT%H%M%SZ") + ".json")
    file.write_text(json.dumps(result, indent=2))
    print(
        "Episode", episode["id"], "status", state["status"], "seconds", round(time.monotonic() - started, 2)
    )
    for frame in result["frames"]:
        data = frame["data"]
        if frame["event"] == "failure":
            print("Failure:", data)
        if frame["event"] == "trace" and data["kind"] in {"model_failure", "critic", "query_rewritten"}:
            print(data["kind"], data["data"])
    if state["status"] == "PENDING_APPROVAL":
        a = state["approval"]
        await client.post(
            "/api/approvals/" + a["id"] + "/decision",
            {
                "action": "approve",
                "proposal_hash": a["hash"],
                "revision": a["revision"],
            },
        )
        committed = await client.run(episode["id"])
        file.write_text(json.dumps({"planning": result, "commit": committed}, indent=2))
        print("Final status", committed["state"]["status"], "ledger", committed["state"]["ledger_id"])
    print("Actual evidence:", file)
    await client.close()


asyncio.run(main())
