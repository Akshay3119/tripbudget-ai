import asyncio
import argparse
import json
import os
import subprocess
from pathlib import Path

import httpx

from evaluation.client import AppClient, default_request
from tripbudget.schemas import utcnow


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="deliverables/evidence/cloud-smoke-new.json")
    args = parser.parse_args()
    destination = Path(args.output)
    if destination.exists():
        raise SystemExit("Refusing to overwrite cloud evidence; choose another output")
    client = AppClient("https://a4-tripbudget-yfvxnchjvq-uc.a.run.app", "cloud-organizer")
    identity_result = await asyncio.to_thread(
        subprocess.run,
        ["gcloud", "auth", "print-identity-token"],
        env=dict(os.environ, CLOUDSDK_CONFIG=str(Path(".runtime/gcloud").resolve())),
        capture_output=True,
        text=True,
        check=True,
    )
    identity = identity_result.stdout.strip()
    client.client.headers["X-Serverless-Authorization"] = "Bearer " + identity
    await client.login()
    record = {
        "at": utcnow().isoformat(),
        "infrastructure": "Cloud Run IAM restricted + Cloud SQL PostgreSQL16",
        "actual_execution": True,
    }
    try:
        record["release"] = await client.get("/api/meta")
        request = default_request(
            days=3,
            cities=["PHL"],
            travelers=[{"id": "t1", "budget_cents": 150000}, {"id": "t2", "budget_cents": 150000}],
        )
        episode = await client.post("/api/episodes", request)
        record["episode"] = episode["id"]
        result = await client.run(episode["id"])
        record["planning"] = result
        if result["state"]["status"] == "PENDING_APPROVAL":
            a = result["state"]["approval"]
            await client.post(
                "/api/approvals/" + a["id"] + "/decision",
                {"action": "approve", "proposal_hash": a["hash"], "revision": a["revision"]},
            )
            record["commit"] = await client.run(episode["id"])
        response = await client.client.post(
            "/api/notes/normalize",
            json={
                "note": "Public synthetic vegetarian note; local endpoint intentionally absent in cloud-only mode."
            },
        )
        record["private_note_without_laptop"] = {"status": response.status_code, "response": response.json()}
        async with httpx.AsyncClient(trust_env=False) as raw:
            response = await raw.get("https://a4-tripbudget-yfvxnchjvq-uc.a.run.app/healthz")
            record["unauthenticated_direct_http_status"] = response.status_code
        record["success"] = (
            record.get("commit", {}).get("state", {}).get("status") == "COMMITTED"
            and record["private_note_without_laptop"]["status"] == 503
            and record["unauthenticated_direct_http_status"] in {401, 403, 404}
        )
    finally:
        destination.write_text(json.dumps(record, indent=2))
        await client.close()
    print("Cloud smoke end-to-end:", record["success"])
    assert record["success"]


if __name__ == "__main__":
    asyncio.run(main())
