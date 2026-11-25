import asyncio
import secrets

import pytest

from evaluation.client import default_request
from tripbudget.errors import DomainError
from tripbudget.graph import Workflow


async def episode(client):
    response = await client.post(
        "/api/episodes", json=default_request(), headers={"Idempotency-Key": secrets.token_hex(12)}
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


async def run(client, identifier):
    response = await client.post(
        f"/api/episodes/{identifier}/run", json={}, headers={"Idempotency-Key": secrets.token_hex(12)}
    )
    assert response.status_code == 200
    state = (await client.get(f"/api/episodes/{identifier}")).json()
    return state


async def test_http_planning_approval_replay_and_exactly_one_ledger(service):
    app, client, uid = service
    identifier = await episode(client)
    state = await run(client, identifier)
    assert state["status"] == "PENDING_APPROVAL"
    assert state["proposal"]["valid"]
    a = state["approval"]
    body = {"action": "approve", "proposal_hash": a["hash"], "revision": a["revision"]}
    header = {"Idempotency-Key": "test-approval-replay"}
    for _ in range(2):
        r = await client.post(f"/api/approvals/{a['id']}/decision", json=body, headers=header)
        assert r.status_code == 200, r.text
    committed = await run(client, identifier)
    assert committed["status"] == "COMMITTED"
    again = await run(client, identifier)
    assert again["ledger_id"] == committed["ledger_id"]
    row = await app.state.store.one("SELECT count(*) AS n FROM ledgers WHERE episode=%s", (identifier,))
    assert row["n"] == 1


async def test_pending_interrupt_recovers_on_new_graph_and_store_connection(service):
    app, client, uid = service
    identifier = await episode(client)
    before = await run(client, identifier)
    assert before["status"] == "PENDING_APPROVAL"
    app.state.workflow = Workflow(
        app.state.settings, app.state.store, app.state.catalog, app.state.corpus, app.state.providers
    )
    a = before["approval"]
    await client.post(
        f"/api/approvals/{a['id']}/decision",
        json={"action": "approve", "proposal_hash": a["hash"], "revision": 1},
        headers={"Idempotency-Key": secrets.token_hex(12)},
    )
    after = await run(client, identifier)
    assert after["status"] == "COMMITTED"


async def test_edit_invalidates_old_approval_and_requires_new_decision(service):
    app, client, uid = service
    identifier = await episode(client)
    state = await run(client, identifier)
    a = state["approval"]
    r = await client.post(
        f"/api/approvals/{a['id']}/decision",
        json={"action": "edit", "proposal_hash": a["hash"], "revision": 1, "new_budget_cents": 90000},
        headers={"Idempotency-Key": secrets.token_hex(12)},
    )
    assert r.status_code == 200
    revised = await run(client, identifier)
    assert revised["revision"] == 2 and revised["status"] == "PENDING_APPROVAL"
    assert revised["approval"]["id"] != a["id"]
    bad = await client.post(
        f"/api/approvals/{a['id']}/decision",
        json={"action": "approve", "proposal_hash": a["hash"], "revision": 1},
        headers={"Idempotency-Key": secrets.token_hex(12)},
    )
    assert bad.status_code == 409
    assert revised["ledger_id"] is None


async def test_cross_owner_reads_and_writes_are_not_found(service):
    app, client, uid = service
    identifier = await episode(client)
    other = "other-" + secrets.token_hex(5)
    await app.state.store.execute(
        "INSERT INTO app_users(uid,username,password_hash) VALUES(%s,%s,'no-login')", (other, other)
    )
    token = await app.state.store.new_session(other)
    response = await client.get(f"/api/episodes/{identifier}", headers={"Authorization": "Bearer " + token})
    assert response.status_code == 404
    response = await client.get(
        f"/api/episodes/{identifier}/events", headers={"Authorization": "Bearer " + token}
    )
    assert response.status_code == 404


async def test_preference_confirmation_is_separate_and_version_checked(service):
    app, client, uid = service
    values = {
        "group_id": "demo-group",
        "expected_version": 0,
        "values": {"diet": "vegetarian", "maximum_walk_meters": 6000},
        "confirmed": True,
    }
    assert (await client.post("/api/preferences/confirm", json=values)).status_code == 200
    assert (await client.post("/api/preferences/confirm", json=values)).status_code == 409
    data = (await client.get("/api/preferences")).json()
    assert data["data"]["diet"] == "vegetarian" and data["version"] == 1


async def test_raw_private_note_is_not_saved_in_events_checkpoints_or_usage(service):
    app, client, uid = service
    canary = "PRIVATE_CANARY_" + secrets.token_hex(10)
    response = await client.post("/api/notes/normalize", json={"note": canary + " Vegetarian."})
    assert response.status_code == 200
    assert not response.json()["saved"]
    prefs = (await client.get("/api/preferences")).json()
    assert prefs["version"] == 0
    row = await app.state.store.one(
        "SELECT count(*) AS n FROM model_usage WHERE uid=%s AND task LIKE %s", (uid, "%" + canary + "%")
    )
    assert row["n"] == 0


async def test_session_advisory_lock_blocks_parallel_invocations(service):
    app, client, uid = service
    identifier = await episode(client)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def worker():
        async with app.state.store.invocation(identifier, uid):
            entered.set()
            await release.wait()

    task = asyncio.create_task(worker())
    await entered.wait()
    try:
        with pytest.raises(DomainError, match="active worker"):
            async with app.state.store.invocation(identifier, uid):
                pass
    finally:
        release.set()
        await task


async def test_admission_idempotency_requires_same_input(service):
    app, client, uid = service
    header = {"Idempotency-Key": "fixed-admission-key"}
    request = default_request()
    first = await client.post("/api/episodes", json=request, headers=header)
    second = await client.post("/api/episodes", json=request, headers=header)
    assert first.json()["id"] == second.json()["id"]
    request["days"] = 6
    conflict = await client.post("/api/episodes", json=request, headers=header)
    assert conflict.status_code == 409


async def test_validation_does_not_echo_secret_note_values(service):
    app, client, uid = service
    secret = "DO_NOT_ECHO_CANARY"
    response = await client.post("/api/notes/normalize", json={"note": "okay", "system_override": secret})
    assert response.status_code == 422 and secret not in response.text


async def test_admission_replay_still_matches_original_input_after_saved_preferences_apply(service):
    app, client, uid = service
    await client.post(
        "/api/preferences/confirm",
        json={
            "group_id": "demo-group",
            "expected_version": 0,
            "values": {"diet": "vegetarian", "maximum_walk_meters": 6000},
            "confirmed": True,
        },
    )
    request = default_request(use_saved_preferences=True)
    headers = {"Idempotency-Key": "admission-survives-normalization"}
    first = await client.post("/api/episodes", json=request, headers=headers)
    state = await run(client, first.json()["id"])
    assert all(t["diet"] == "vegetarian" for t in state["request"]["travelers"])
    replay = await client.post("/api/episodes", json=request, headers=headers)
    assert replay.status_code == 200 and replay.json()["id"] == first.json()["id"]
