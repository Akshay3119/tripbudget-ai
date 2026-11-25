"""Actual operating-system/API/DB fault tests on an isolated development serving process."""

import asyncio
import os
import signal
import sys
import uuid
from pathlib import Path


from tripbudget.persistence import Store
from tripbudget.providers import Providers
from tripbudget.resources import Budget
from tripbudget.schemas import ModelPreferences, QueryRewrite, utcnow
from tripbudget.settings import Settings

from .client import AppClient, default_request
from .run_eval import append_record, wait_ready


async def main():
    out = Path("deliverables/evidence/operations.jsonl")
    if out.exists():
        raise SystemExit("Refusing overwrite")
    s = Settings()
    store = Store(s)
    process = None
    log = None
    client = None

    async def start():
        nonlocal process, log, client
        log = await asyncio.to_thread(open, ".runtime/logs/operations-app.log", "a")
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "uvicorn",
            "tripbudget.api:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8088",
            "--no-access-log",
            env=dict(os.environ, TRIPBUDGET_ENABLE_TEST_CONTROLS="true"),
            stdout=log,
            stderr=log,
        )
        await wait_ready("http://127.0.0.1:8088", process)
        client = await AppClient("http://127.0.0.1:8088", "operations").login()

    async def stop():
        await client.close()
        process.send_signal(signal.SIGTERM)
        await asyncio.wait_for(process.wait(), 15)
        log.close()

    async def plan(**changes):
        req = default_request(
            days=3,
            cities=["NYC"],
            travelers=[{"id": "t1", "budget_cents": 150000}, {"id": "t2", "budget_cents": 150000}],
            **changes,
        )
        ep = (await client.post("/api/episodes", req))["id"]
        result = await client.run(ep)
        assert result["state"]["status"] == "PENDING_APPROVAL", result["state"]["status"]
        return ep, result

    async def decision(state, action="approve", key=None, **extra):
        a = state["approval"]
        return await client.post(
            "/api/approvals/" + a["id"] + "/decision",
            {"action": action, "proposal_hash": a["hash"], "revision": a["revision"], **extra},
            key=key,
        )

    async def check(identifier, function):
        record = {
            "id": identifier,
            "at": utcnow().isoformat(),
            "infrastructure": "actual local process + PostgreSQL; real providers; explicit faults labeled",
            "actual_execution": True,
        }
        try:
            record["observation"] = await function()
            record["success"] = True
        except Exception as exc:
            record.update(
                success=False,
                error=getattr(exc, "code", type(exc).__name__),
                detail=str(exc)[:140] if isinstance(exc, AssertionError) else "See isolated operation trace",
            )
        append_record(out, record)
        print(identifier, record["success"], flush=True)

    await start()
    uid = (await client.get("/api/meta"))["uid"]
    saved = {}

    async def o01():
        ep, r = await plan()
        old = await client.get("/api/meta")
        h = r["state"]["approval"]["hash"]
        await stop()
        await start()
        new = await client.get("/api/meta")
        state = await client.get("/api/episodes/" + ep)
        assert old["boot_id"] != new["boot_id"] and state["approval"]["hash"] == h
        saved.update(ep=ep, state=state, key=uuid.uuid4().hex)
        await decision(state, key=saved["key"])
        done = await client.run(ep)
        assert done["state"]["status"] == "COMMITTED"
        saved["ledger"] = done["state"]["ledger_id"]
        return {
            "episode": ep,
            "old_boot": old["boot_id"],
            "new_boot": new["boot_id"],
            "proposal_hash": h,
            "ledger": saved["ledger"],
        }

    async def o02():
        await decision(saved["state"], key=saved["key"])
        await client.run(saved["ep"])
        row = await store.one("SELECT count(*) AS n FROM ledgers WHERE episode=%s", (saved["ep"],))
        assert row["n"] == 1
        return {"episode": saved["ep"], "ledgers": 1, "same_decision_key_replayed": True}

    async def o03():
        ep, r = await plan()
        a = r["state"]["approval"]
        await decision(r["state"], "edit", new_budget_cents=140000)
        revised = await client.run(ep)
        assert revised["state"]["revision"] == 2 and not revised["state"]["ledger_id"]
        response = await client.client.post(
            "/api/approvals/" + a["id"] + "/decision",
            json={"action": "approve", "proposal_hash": a["hash"], "revision": a["revision"]},
            headers={"Idempotency-Key": uuid.uuid4().hex},
        )
        assert response.status_code == 409
        return {
            "episode": ep,
            "new_revision": 2,
            "old_approval_response": response.json(),
            "outcome": revised["state"]["status"],
        }

    async def o04():
        ep = (await client.post("/api/episodes", default_request()))["id"]
        async with store.invocation(ep, uid):
            r = await client.run(ep)
        assert any(f["event"] == "failure" and f["data"]["error"] == "RUN_BUSY" for f in r["frames"])
        return {"episode": ep, "failure": "RUN_BUSY", "owner_lock_held_by_other_session": True}

    async def o05():
        ep, r = await plan()
        a = r["state"]["approval"]
        await store.execute(
            "UPDATE approvals SET expires_at=now()-interval '1 second' WHERE id=%s", (a["id"],)
        )
        response = await client.client.post(
            "/api/approvals/" + a["id"] + "/decision",
            json={"action": "approve", "proposal_hash": a["hash"], "revision": a["revision"]},
            headers={"Idempotency-Key": uuid.uuid4().hex},
        )
        assert response.status_code == 409 and response.json()["error"] == "APPROVAL_EXPIRED"
        return {
            "episode": ep,
            "fault": "operator expired evidence/approval row",
            "response": response.json(),
            "ledger": (await client.get("/api/episodes/" + ep))["ledger_id"],
        }

    async def o06():
        ep = (
            await client.post(
                "/api/episodes",
                default_request(
                    days=3,
                    cities=["NYC"],
                    travelers=[{"id": "t1", "budget_cents": 150000}, {"id": "t2", "budget_cents": 150000}],
                ),
            )
        )["id"]
        r = await client.run(ep, simulate_cloud_429=True)
        events = [f["data"] for f in r["frames"] if f["event"] == "trace"]
        assert any(
            e["kind"] == "model_failure" and e["data"].get("error") == "CLOUD_429_SIMULATED" for e in events
        )
        assert any(e["kind"] == "model_result" and e["data"].get("provider") == "local" for e in events)
        return {
            "episode": ep,
            "fault": "authenticated explicitly simulated 429; actual local completion",
            "outcome": r["state"]["status"],
            "frames": r["frames"],
        }

    async def o07():
        bad = s.model_copy(update={"ollama_url": "http://127.0.0.1:59999", "provider_timeout": 3})
        before = utcnow()
        try:
            await Providers(bad).complete(
                "preference_parse",
                ModelPreferences,
                {"untrusted_note": "Public synthetic vegetarian test note"},
                Budget(store, None, uid),
                restricted=True,
            )
        except Exception as exc:
            assert getattr(exc, "code", None) == "LOCAL_UNAVAILABLE"
        else:
            raise AssertionError("Unavailable local endpoint unexpectedly completed")
        usage = await store.all(
            "SELECT provider,task,success,error FROM model_usage WHERE uid=%s AND episode IS NULL AND at>=%s",
            (uid, before),
        )
        assert usage and all(x["provider"] == "local" for x in usage)
        return {"fault": "local endpoint unreachable", "usage": usage, "cloud_egress": False}

    async def o08():
        bad = s.model_copy(update={"ollama_url": "http://127.0.0.1:59999", "provider_timeout": 15})
        ep = (await client.post("/api/episodes", default_request()))["id"]
        result = await Providers(bad).complete(
            "query_rewrite",
            QueryRewrite,
            {"instruction": "Rewrite a public query for NYC museum admission and opening hours"},
            Budget(store, ep, uid),
        )
        usage = await store.all("SELECT provider,success,error FROM model_usage WHERE episode=%s", (ep,))
        assert any(x["provider"] == "cloud" and x["success"] for x in usage)
        return {
            "episode": ep,
            "fault": "public utility local endpoint unreachable",
            "result": result.model_dump(),
            "usage": usage,
        }

    async def o09():
        ep = (await client.post("/api/episodes", default_request(days=3, cities=["PHL"])))["id"]
        async with client.client.stream(
            "POST", "/api/episodes/" + ep + "/run", json={}, headers={"Idempotency-Key": uuid.uuid4().hex}
        ) as response:
            async for line in response.aiter_lines():
                if line.startswith("data:"):
                    break
        await asyncio.sleep(0.5)
        before = await client.get("/api/episodes/" + ep + "/events")
        recovered = await client.run(ep)
        assert before and not recovered["state"]["ledger_id"]
        return {
            "episode": ep,
            "durable_events_before_reconnect": len(before),
            "recovered_outcome": recovered["state"]["status"],
            "no_unapproved_commit": True,
        }

    async def o10():
        ep, r = await plan()
        await decision(r["state"])
        lost = False
        try:
            async with store.invocation(ep, uid):
                pid = (await store.one("SELECT pg_backend_pid() AS pid"))["pid"]
                async with store.connection(fresh=True) as killer:
                    await killer.execute("SELECT pg_terminate_backend(%s)", (pid,))
                await store.execute("UPDATE episodes SET status='UNREACHABLE_SENTINEL' WHERE id=%s", (ep,))
        except Exception:
            lost = True
        assert lost
        row = await store.one("SELECT count(*) AS n FROM ledgers WHERE episode=%s", (ep,))
        assert row["n"] == 0
        resumed = await client.run(ep)
        row = await store.one("SELECT count(*) AS n FROM ledgers WHERE episode=%s", (ep,))
        assert row["n"] == 1
        return {
            "episode": ep,
            "fault": "actual pg_terminate_backend of invocation session after human approval",
            "before_resume_ledgers": 0,
            "after_resume_ledgers": 1,
            "outcome": resumed["state"]["status"],
        }

    async def o11():
        other = await AppClient("http://127.0.0.1:8088", "evaluator").login()
        try:
            codes = [
                (await other.client.get(path)).status_code
                for path in ["/api/episodes/" + saved["ep"], "/api/ledgers/" + saved["ledger"]]
            ]
            assert codes == [404, 404]
            return {"foreign_episode_and_ledger_status": codes}
        finally:
            await other.close()

    async def o12():
        group = "restart-memory-" + uuid.uuid4().hex[:8]
        await client.post(
            "/api/preferences/confirm",
            {
                "group_id": group,
                "expected_version": 0,
                "values": {"diet": "vegetarian", "maximum_walk_meters": 6000, "preferred_categories": []},
                "confirmed": True,
            },
        )
        old = await client.get("/api/meta")
        await stop()
        await start()
        new = await client.get("/api/meta")
        ep, r = await plan(group_id=group, use_saved_preferences=True)
        assert old["boot_id"] != new["boot_id"] and all(
            t["diet"] == "vegetarian" and t["maximum_walk_meters"] == 6000
            for t in r["state"]["request"]["travelers"]
        )
        return {
            "episode": ep,
            "old_boot": old["boot_id"],
            "new_boot": new["boot_id"],
            "later_request": r["state"]["request"],
            "outcome": r["state"]["status"],
        }

    try:
        for i, f in enumerate([o01, o02, o03, o04, o05, o06, o07, o08, o09, o10, o11, o12], 1):
            await check(f"O{i:02}", f)
    finally:
        await stop()


if __name__ == "__main__":
    asyncio.run(main())
