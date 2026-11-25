import json
import uuid
from datetime import date, timedelta
from pathlib import Path

import httpx


def default_request(**changes):
    request = {
        "start_date": (date.today() + timedelta(days=3)).isoformat(),
        "days": 5,
        "cities": ["NYC", "PHL", "DC"],
        "travelers": [{"id": f"t{i + 1}", "budget_cents": 85000} for i in range(4)],
        "estimates_confirmed": True,
        "use_saved_preferences": False,
    }
    request.update(changes)
    return request


class AppClient:
    def __init__(self, url="http://127.0.0.1:8084", username="evaluator"):
        self.url, self.username = url, username
        self.client = httpx.AsyncClient(base_url=url, timeout=300, trust_env=False)
        self.token = ""

    async def login(self):
        values = dict(
            line.split("=", 1) for line in Path(f".secrets/{self.username}.txt").read_text().splitlines()
        )
        response = await self.client.post("/api/login", json=values)
        response.raise_for_status()
        self.token = response.json()["token"]
        self.client.headers["Authorization"] = "Bearer " + self.token
        return self

    async def post(self, path, data, key=None):
        response = await self.client.post(
            path, json=data, headers={"Idempotency-Key": key or uuid.uuid4().hex}
        )
        response.raise_for_status()
        return response.json()

    async def get(self, path):
        response = await self.client.get(path)
        response.raise_for_status()
        return response.json()

    async def run(self, episode, **options):
        frames = []
        async with self.client.stream(
            "POST",
            f"/api/episodes/{episode}/run",
            json=options,
            headers={"Idempotency-Key": uuid.uuid4().hex},
        ) as response:
            response.raise_for_status()
            event = None
            async for line in response.aiter_lines():
                if line.startswith("event: "):
                    event = line[7:]
                elif line.startswith("data: "):
                    frames.append({"event": event, "data": json.loads(line[6:])})
        return {"state": await self.get(f"/api/episodes/{episode}"), "frames": frames}

    async def close(self):
        await self.client.aclose()
