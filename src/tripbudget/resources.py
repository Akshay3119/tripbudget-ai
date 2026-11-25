import time
import uuid

from .errors import DomainError


class Budget:
    def __init__(self, store, episode, uid):
        self.store, self.episode, self.uid = store, episode, uid
        self.started = time.monotonic()
        self.local_calls = 0

    async def remaining_seconds(self):
        if self.episode is None:
            return max(0.0, 45 - (time.monotonic() - self.started))
        row = await self.store.one("SELECT active_ms FROM episodes WHERE id=%s", (self.episode,))
        return max(
            0.0,
            self.store.settings.active_seconds - row["active_ms"] / 1000 - (time.monotonic() - self.started),
        )

    async def reserve(self, task, provider, model, input_bound, output_bound, logical=True):
        s = self.store.settings
        if await self.remaining_seconds() <= 0:
            raise DomainError("RESOURCE_LIMIT", "Active planning time exhausted")
        if self.episode is None:
            self.local_calls += 1
            if self.local_calls > 1:
                raise DomainError("RESOURCE_LIMIT", "Restricted note gets one local attempt")
        identifier = uuid.uuid4().hex
        async with self.store.operation() as conn, conn.transaction():
            if self.episode:
                row = await (
                    await conn.execute(
                        "UPDATE episodes SET calls=calls+%s,attempts=attempts+1,tokens=tokens+%s,"
                        "output_tokens=output_tokens+%s WHERE id=%s AND calls+%s<=%s AND attempts+1<=%s "
                        "AND tokens+%s<=%s AND output_tokens+%s<=%s RETURNING id",
                        (
                            int(logical),
                            input_bound + output_bound,
                            output_bound,
                            self.episode,
                            int(logical),
                            s.max_calls,
                            s.max_attempts,
                            input_bound + output_bound,
                            s.max_tokens,
                            output_bound,
                            s.max_output_tokens,
                        ),
                    )
                ).fetchone()
                if not row:
                    raise DomainError("RESOURCE_LIMIT", "Persisted model-call/token budget exhausted")
            await conn.execute(
                "INSERT INTO model_usage(id,episode,uid,task,provider,model,reserved,reserved_output) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    identifier,
                    self.episode,
                    self.uid,
                    task,
                    provider,
                    model,
                    input_bound + output_bound,
                    output_bound,
                ),
            )
        return identifier

    async def settle(self, usage_id, input_tokens, output_tokens, reasoning, latency_ms, success, error=None):
        # Unknown failures keep their conservative reservation. Success requires reported usage.
        async with self.store.operation() as conn, conn.transaction():
            row = await (
                await conn.execute("SELECT * FROM model_usage WHERE id=%s FOR UPDATE", (usage_id,))
            ).fetchone()
            await conn.execute(
                "UPDATE model_usage SET input_tokens=%s,output_tokens=%s,reasoning_tokens=%s,latency_ms=%s,"
                "success=%s,error=%s WHERE id=%s",
                (input_tokens, output_tokens, reasoning, latency_ms, success, error, usage_id),
            )
            if self.episode and input_tokens is not None and output_tokens is not None:
                await conn.execute(
                    "UPDATE episodes SET tokens=tokens-%s+%s,output_tokens=output_tokens-%s+%s WHERE id=%s",
                    (
                        row["reserved"],
                        input_tokens + output_tokens,
                        row["reserved_output"],
                        output_tokens,
                        self.episode,
                    ),
                )

    async def external(self, kind):
        if kind not in {"searches", "fetches"}:
            raise ValueError("Unknown external-call counter")
        if not self.episode:
            raise DomainError("PERMISSION_DENIED", "Notes cannot call external tools", 403)
        # Column identifier is chosen from a fixed server enum, never from model/user text.
        row = await self.store.one(
            f"UPDATE episodes SET {kind}={kind}+1 WHERE id=%s AND {kind}<4 RETURNING id", (self.episode,)
        )
        if not row:
            raise DomainError("RESOURCE_LIMIT", "External-call budget exhausted")
