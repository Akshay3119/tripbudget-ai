import asyncio
import contextvars
import hashlib
import json
import secrets
import uuid
from contextlib import asynccontextmanager
from datetime import timedelta

import psycopg
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .errors import DomainError
from .schemas import utcnow

SCHEMA = """
CREATE TABLE IF NOT EXISTS app_users (
 uid TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
 role TEXT NOT NULL DEFAULT 'organizer' CHECK(role IN ('organizer','evaluation','admin')));
CREATE TABLE IF NOT EXISTS app_sessions (
 token_hash TEXT PRIMARY KEY, uid TEXT NOT NULL REFERENCES app_users(uid), expires_at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS preferences (
 uid TEXT NOT NULL, group_id TEXT NOT NULL, version INTEGER NOT NULL, data JSONB NOT NULL,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), PRIMARY KEY(uid,group_id));
CREATE TABLE IF NOT EXISTS episodes (
 id TEXT PRIMARY KEY, lock_id BIGSERIAL UNIQUE NOT NULL, uid TEXT NOT NULL,
 request JSONB NOT NULL, status TEXT NOT NULL DEFAULT 'NEW', revision INTEGER NOT NULL DEFAULT 1,
 calls INTEGER NOT NULL DEFAULT 0, attempts INTEGER NOT NULL DEFAULT 0,
 tokens INTEGER NOT NULL DEFAULT 0, output_tokens INTEGER NOT NULL DEFAULT 0,
 searches INTEGER NOT NULL DEFAULT 0, fetches INTEGER NOT NULL DEFAULT 0,
 active_ms BIGINT NOT NULL DEFAULT 0, admission_key TEXT NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE(uid,admission_key));
ALTER TABLE episodes ADD COLUMN IF NOT EXISTS admission_hash TEXT;
ALTER TABLE episodes ADD COLUMN IF NOT EXISTS active_started_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS episodes_owner_date ON episodes(uid,created_at);
CREATE TABLE IF NOT EXISTS proposals (
 episode TEXT NOT NULL REFERENCES episodes(id), revision INTEGER NOT NULL,
 hash TEXT NOT NULL, payload JSONB NOT NULL, expires_at TIMESTAMPTZ NOT NULL,
 PRIMARY KEY(episode,revision));
CREATE TABLE IF NOT EXISTS approvals (
 id TEXT PRIMARY KEY, episode TEXT NOT NULL, revision INTEGER NOT NULL, uid TEXT NOT NULL,
 hash TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'PENDING', decision JSONB,
 decision_key TEXT, expires_at TIMESTAMPTZ NOT NULL,
 UNIQUE(episode,revision), FOREIGN KEY(episode,revision) REFERENCES proposals(episode,revision));
CREATE TABLE IF NOT EXISTS ledgers (
 id TEXT PRIMARY KEY, episode TEXT NOT NULL, revision INTEGER NOT NULL, uid TEXT NOT NULL,
 hash TEXT NOT NULL, payload JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE(episode,revision), FOREIGN KEY(episode,revision) REFERENCES proposals(episode,revision));
CREATE TABLE IF NOT EXISTS events (
 id BIGSERIAL PRIMARY KEY, episode TEXT NOT NULL REFERENCES episodes(id), kind TEXT NOT NULL,
 data JSONB NOT NULL, at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS model_usage (
 id TEXT PRIMARY KEY, episode TEXT REFERENCES episodes(id), uid TEXT NOT NULL,
 task TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL,
 reserved INTEGER NOT NULL, reserved_output INTEGER NOT NULL,
 input_tokens INTEGER, output_tokens INTEGER, reasoning_tokens INTEGER,
 success BOOLEAN NOT NULL DEFAULT false, latency_ms INTEGER, error TEXT,
 at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS note_requests (
 id TEXT PRIMARY KEY, uid TEXT NOT NULL, at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS auth_attempts (
 key TEXT PRIMARY KEY, attempts INTEGER NOT NULL, window_start TIMESTAMPTZ NOT NULL);
"""


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class ReentrantSessionLock:
    """Serialize the official saver's pipeline and app transactions on one owned session."""

    def __init__(self):
        self.lock = asyncio.Lock()
        self.owner = None
        self.depth = 0

    async def __aenter__(self):
        task = asyncio.current_task()
        if self.owner is not task:
            await self.lock.acquire()
            self.owner = task
        self.depth += 1
        return self

    async def __aexit__(self, *_):
        self.depth -= 1
        if not self.depth:
            self.owner = None
            self.lock.release()


class Store:
    """External PostgreSQL authority. Invocation ownership and checkpoint writes share one session."""

    def __init__(self, settings):
        self.settings = settings
        self.connection_gate = asyncio.Semaphore(8)
        self.current = contextvars.ContextVar("tripbudget_connection", default=None)
        self.current_lock = contextvars.ContextVar("tripbudget_session_lock", default=None)

    @asynccontextmanager
    async def connection(self, fresh=False):
        existing = self.current.get()
        if existing is not None and not fresh:
            yield existing
            return
        async with (
            self.connection_gate,
            await psycopg.AsyncConnection.connect(
                self.settings.database_url.get_secret_value(),
                autocommit=True,
                row_factory=dict_row,
                prepare_threshold=0,
                connect_timeout=10,
            ) as conn,
        ):
            context = self.current.set(conn)
            lock_context = self.current_lock.set(ReentrantSessionLock())
            try:
                yield conn
            finally:
                self.current_lock.reset(lock_context)
                self.current.reset(context)

    @asynccontextmanager
    async def operation(self):
        async with self.connection() as conn, self.current_lock.get():
            yield conn

    async def migrate(self):
        async with self.connection() as conn:
            await conn.execute(SCHEMA, prepare=False)
            # Standard documented integration; setup runs only in the operator migration command.
            await AsyncPostgresSaver(conn).setup()

    async def one(self, sql, args=()):
        async with self.operation() as conn:
            return await (await conn.execute(sql, args)).fetchone()

    async def all(self, sql, args=()):
        async with self.operation() as conn:
            return await (await conn.execute(sql, args)).fetchall()

    async def execute(self, sql, args=()):
        async with self.operation() as conn:
            return await conn.execute(sql, args)

    async def event(self, episode, kind, data):
        return await self.one(
            "INSERT INTO events(episode,kind,data) VALUES(%s,%s,%s) RETURNING id,kind,data,at",
            (episode, kind, Jsonb(data)),
        )

    async def owned_episode(self, episode, uid):
        row = await self.one("SELECT * FROM episodes WHERE id=%s AND uid=%s", (episode, uid))
        if not row:
            raise DomainError("NOT_FOUND", "Episode not found", 404)
        return row

    @asynccontextmanager
    async def invocation(self, episode, uid):
        async with self.connection(fresh=True) as conn:
            row = await (
                await conn.execute("SELECT lock_id FROM episodes WHERE id=%s AND uid=%s", (episode, uid))
            ).fetchone()
            if not row:
                raise DomainError("NOT_FOUND", "Episode not found", 404)
            owner_lock = await (
                await conn.execute("SELECT pg_try_advisory_lock(310599,hashtext(%s)) AS ok", (uid,))
            ).fetchone()
            if not owner_lock["ok"]:
                raise DomainError("RUN_BUSY", "This organizer already has an active worker", 409)
            lock = await (
                await conn.execute("SELECT pg_try_advisory_lock(%s) AS ok", (row["lock_id"],))
            ).fetchone()
            if not lock["ok"]:
                raise DomainError("RUN_BUSY", "This episode already has an active worker", 409)
            token = self.current.set(conn)
            try:
                yield conn
            finally:
                self.current.reset(token)
                if not conn.closed:
                    await conn.execute("SELECT pg_advisory_unlock(%s)", (row["lock_id"],))
                    await conn.execute("SELECT pg_advisory_unlock(310599,hashtext(%s))", (uid,))

    async def admit(self, uid, request, key, quota):
        async with self.operation() as conn, conn.transaction():
            # Serialize per-owner admissions; idempotency is checked before quota.
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("admit:" + uid,))
            old = await (
                await conn.execute("SELECT * FROM episodes WHERE uid=%s AND admission_key=%s", (uid, key))
            ).fetchone()
            if old:
                if (old["admission_hash"] or digest(old["request"])) != digest(request):
                    raise DomainError("IDEMPOTENCY_CONFLICT", "Key already used with different input", 409)
                return old
            count = await (
                await conn.execute(
                    "SELECT count(*) AS n FROM episodes WHERE uid=%s AND created_at>now()-interval '1 day'",
                    (uid,),
                )
            ).fetchone()
            if count["n"] >= quota:
                raise DomainError("RATE_LIMIT", "Daily planning quota reached", 429)
            episode = uuid.uuid4().hex
            row = await (
                await conn.execute(
                    "INSERT INTO episodes(id,uid,request,admission_key,admission_hash) VALUES(%s,%s,%s,%s,%s) RETURNING *",
                    (episode, uid, Jsonb(request), key, digest(request)),
                )
            ).fetchone()
            await self.event(episode, "admitted", {"constraints_hash": digest(request)})
            return row

    async def preferences(self, uid, group):
        row = await self.one(
            "SELECT version,data FROM preferences WHERE uid=%s AND group_id=%s", (uid, group)
        )
        return row or {"version": 0, "data": None}

    async def save_preferences(self, uid, confirmation):
        async with self.operation() as conn, conn.transaction():
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s))", ("pref:" + uid + confirmation.group_id,)
            )
            previous = await self.preferences(uid, confirmation.group_id)
            if previous["version"] != confirmation.expected_version:
                raise DomainError("VERSION_CONFLICT", "Preferences changed; reload before confirming", 409)
            version = previous["version"] + 1
            values = confirmation.values.model_dump()
            await conn.execute(
                "INSERT INTO preferences(uid,group_id,version,data) VALUES(%s,%s,%s,%s) "
                "ON CONFLICT(uid,group_id) DO UPDATE SET version=excluded.version,data=excluded.data,updated_at=now()",
                (uid, confirmation.group_id, version, Jsonb(values)),
            )
            return {"version": version, "data": values}

    async def persist_proposal(self, episode, uid, revision, proposal, expires_at):
        hash_ = digest(proposal)
        async with self.operation() as conn, conn.transaction():
            old = await (
                await conn.execute(
                    "SELECT * FROM proposals WHERE episode=%s AND revision=%s", (episode, revision)
                )
            ).fetchone()
            if old and old["hash"] != hash_:
                raise DomainError("REVISION_CONFLICT", "Immutable proposal revision already exists", 409)
            await conn.execute(
                "INSERT INTO proposals(episode,revision,hash,payload,expires_at) VALUES(%s,%s,%s,%s,%s) "
                "ON CONFLICT DO NOTHING",
                (episode, revision, hash_, Jsonb(proposal), expires_at),
            )
            await conn.execute(
                "INSERT INTO approvals(id,episode,revision,uid,hash,expires_at) VALUES(%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT(episode,revision) DO NOTHING",
                (secrets.token_urlsafe(24), episode, revision, uid, hash_, expires_at),
            )
            await conn.execute(
                "UPDATE episodes SET status='PENDING_APPROVAL',revision=%s,updated_at=now() WHERE id=%s",
                (revision, episode),
            )
            return await (
                await conn.execute(
                    "SELECT * FROM approvals WHERE episode=%s AND revision=%s", (episode, revision)
                )
            ).fetchone()

    async def record_decision(self, uid, approval_id, decision, key):
        async with self.operation() as conn, conn.transaction():
            row = await (
                await conn.execute(
                    "SELECT a.*,e.revision AS current_revision FROM approvals a JOIN episodes e ON e.id=a.episode "
                    "WHERE a.id=%s AND a.uid=%s FOR UPDATE OF a,e",
                    (approval_id, uid),
                )
            ).fetchone()
            if not row:
                raise DomainError("NOT_FOUND", "Approval not found", 404)
            data = decision.model_dump()
            if row["decision_key"] == key:
                if row["decision"] != data:
                    raise DomainError("IDEMPOTENCY_CONFLICT", "Decision key has different contents", 409)
                return row
            if row["status"] != "PENDING" or row["current_revision"] != decision.revision:
                raise DomainError("STALE_APPROVAL", "This approval has already changed", 409)
            if row["hash"] != decision.proposal_hash or row["revision"] != decision.revision:
                raise DomainError("HASH_MISMATCH", "Approval does not match this exact proposal", 409)
            if row["expires_at"] <= utcnow():
                raise DomainError("APPROVAL_EXPIRED", "Evidence or approval expired; replan", 409)
            row = await (
                await conn.execute(
                    "UPDATE approvals SET status='DECIDED',decision=%s,decision_key=%s WHERE id=%s RETURNING *",
                    (Jsonb(data), key, approval_id),
                )
            ).fetchone()
            await self.event(
                row["episode"], "human_decision", {"action": decision.action, "revision": decision.revision}
            )
            return row

    async def commit_approved(self, uid, approval_id, validate):
        async with self.operation() as conn, conn.transaction():
            a = await (
                await conn.execute(
                    "SELECT a.*,p.payload,e.request,e.revision AS current_revision FROM approvals a "
                    "JOIN proposals p ON p.episode=a.episode AND p.revision=a.revision "
                    "JOIN episodes e ON e.id=a.episode WHERE a.id=%s AND a.uid=%s FOR UPDATE OF a,e,p",
                    (approval_id, uid),
                )
            ).fetchone()
            if not a:
                raise DomainError("NOT_FOUND", "Approval not found", 404)
            old = await (
                await conn.execute(
                    "SELECT * FROM ledgers WHERE episode=%s AND revision=%s", (a["episode"], a["revision"])
                )
            ).fetchone()
            if old:
                return old
            if (
                a["status"] != "DECIDED"
                or not a["decision"]
                or a["decision"]["action"] != "approve"
                or a["current_revision"] != a["revision"]
            ):
                raise DomainError("APPROVAL_REQUIRED", "Only a current human decision can save a ledger", 409)
            if a["expires_at"] <= utcnow() or digest(a["payload"]) != a["hash"]:
                raise DomainError("STALE_APPROVAL", "Approval expired or proposal changed", 409)
            validate(a["payload"], a["request"])
            ledger = await (
                await conn.execute(
                    "INSERT INTO ledgers(id,episode,revision,uid,hash,payload) VALUES(%s,%s,%s,%s,%s,%s) RETURNING *",
                    (uuid.uuid4().hex, a["episode"], a["revision"], uid, a["hash"], Jsonb(a["payload"])),
                )
            ).fetchone()
            await conn.execute("UPDATE approvals SET status='CONSUMED' WHERE id=%s", (approval_id,))
            await conn.execute(
                "UPDATE episodes SET status='COMMITTED',updated_at=now() WHERE id=%s", (a["episode"],)
            )
            await self.event(a["episode"], "ledger_committed", {"ledger_id": ledger["id"], "hash": a["hash"]})
            return ledger

    async def change_constraints(self, episode, uid, decision):
        async with self.operation() as conn, conn.transaction():
            row = await self.owned_episode(episode, uid)
            if row["revision"] >= 4:
                raise DomainError("RESOURCE_LIMIT", "Three replans per episode are allowed")
            request = row["request"]
            if decision["action"] == "edit":
                for traveler in request["travelers"]:
                    traveler["budget_cents"] = decision["new_budget_cents"]
            await conn.execute(
                "UPDATE approvals SET status='SUPERSEDED' WHERE episode=%s AND status!='CONSUMED'", (episode,)
            )
            await conn.execute(
                "UPDATE episodes SET request=%s,revision=revision+1,status='RUNNING' WHERE id=%s",
                (Jsonb(request), episode),
            )
            return request

    async def new_session(self, uid):
        token = secrets.token_urlsafe(40)
        await self.execute(
            "INSERT INTO app_sessions(token_hash,uid,expires_at) VALUES(%s,%s,%s)",
            (hashlib.sha256(token.encode()).hexdigest(), uid, utcnow() + timedelta(hours=8)),
        )
        return token
