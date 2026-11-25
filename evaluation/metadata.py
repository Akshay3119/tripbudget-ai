"""Capture configured, real model/backend and source identities without credentials."""

import hashlib
from pathlib import Path

import httpx

from tripbudget.schemas import utcnow


async def release_metadata(client, settings):
    sources = sorted(Path("src").rglob("*.py")) + [Path("pyproject.toml"), Path("uv.lock")]
    digests = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    metadata = {
        "at": utcnow().isoformat(),
        "release": await client.get("/api/meta"),
        "source_files": digests,
        "method": "real endpoints, unchanged graders; isolated sequential suites, not concurrent provider load",
    }
    async with httpx.AsyncClient(trust_env=False, timeout=10) as http:
        try:
            shown = await http.post(settings.ollama_url + "/api/show", json={"model": settings.ollama_model})
            shown.raise_for_status()
            tags = (await http.get(settings.ollama_url + "/api/tags")).json()
            tag = next(
                (
                    m
                    for m in tags.get("models", [])
                    if m["name"] in {settings.ollama_model, settings.ollama_model + ":latest"}
                ),
                {},
            )
            metadata["local_model"] = {
                "name": settings.ollama_model,
                "details": shown.json().get("details"),
                "digest": tag.get("digest"),
                "ollama": (await http.get(settings.ollama_url + "/api/version")).json(),
            }
        except httpx.HTTPError as exc:
            metadata["local_model"] = {"name": settings.ollama_model, "inspection_error": type(exc).__name__}
    return metadata
