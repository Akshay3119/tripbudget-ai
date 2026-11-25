import asyncio
import secrets

import pytest

from evaluation.client import default_request
from tripbudget.errors import DomainError
from tripbudget.resources import Budget
from tripbudget.schemas import utcnow


async def test_resource_reservations_survive_new_budget_object(service):
    app, client, uid = service
    store = app.state.store
    row = await store.admit(uid, default_request(), secrets.token_hex(12), 300)
    await store.execute("UPDATE episodes SET calls=24 WHERE id=%s", (row["id"],))
    budget = Budget(store, row["id"], uid)
    with pytest.raises(DomainError, match="budget exhausted"):
        await budget.reserve("supervisor", "cloud", "test", 100, 100)
    budget = Budget(store, row["id"], uid)
    with pytest.raises(DomainError):
        await budget.reserve("supervisor", "cloud", "test", 100, 100)


async def test_unknown_failed_usage_keeps_conservative_reservation(service):
    app, client, uid = service
    store = app.state.store
    row = await store.admit(uid, default_request(), secrets.token_hex(12), 300)
    budget = Budget(store, row["id"], uid)
    usage = await budget.reserve("supervisor", "cloud", "test", 100, 100)
    await budget.settle(usage, None, None, None, 20, False, "HTTP_429")
    state = await store.owned_episode(row["id"], uid)
    assert state["tokens"] == 200 and state["output_tokens"] == 100


async def test_known_usage_settles_reservation_without_resetting_attempt_count(service):
    app, client, uid = service
    store = app.state.store
    row = await store.admit(uid, default_request(), secrets.token_hex(12), 300)
    budget = Budget(store, row["id"], uid)
    usage = await budget.reserve("supervisor", "cloud", "test", 100, 100)
    await budget.settle(usage, 30, 20, None, 20, True)
    state = await store.owned_episode(row["id"], uid)
    assert state["tokens"] == 50 and state["output_tokens"] == 20 and state["attempts"] == 1


async def test_checkpoint_writer_and_business_transactions_share_session_lock(service):
    app, client, uid = service
    store = app.state.store
    row = await store.admit(uid, default_request(), secrets.token_hex(12), 300)
    async with store.invocation(row["id"], uid) as conn:
        lock = store.current_lock.get()

        async def pipeline_writer():
            for _ in range(20):
                async with lock, conn.pipeline():
                    await conn.execute("SELECT 1 AS ok")

        async def business_writer():
            for _ in range(20):
                async with store.operation() as business_conn, business_conn.transaction():
                    await store.event(row["id"], "test_serialization", {"at": utcnow().isoformat()})

        await asyncio.gather(pipeline_writer(), business_writer())
    events = await store.one(
        "SELECT count(*) AS n FROM events WHERE episode=%s AND kind='test_serialization'", (row["id"],)
    )
    assert events["n"] == 20
