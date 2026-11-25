"""Six current-data checks: actual MCP discovery plus actual official HTTPS fetch per city."""

import asyncio
import hashlib
from pathlib import Path

from tripbudget.persistence import Store
from tripbudget.resources import Budget
from tripbudget.schemas import utcnow
from tripbudget.settings import Settings
from tripbudget.tools import official_source, public_search

from .client import AppClient, default_request
from .run_eval import append_record


async def main():
    out = Path("deliverables/evidence/live-sources-v1.jsonl")
    if out.exists():
        raise SystemExit("Refusing overwrite")
    s = Settings()
    store = Store(s)
    client = await AppClient(username="sources").login()
    uid = (await client.get("/api/meta"))["uid"]
    for city, url in [
        ("NYC", "https://www.nyc.gov/html/dot/html/ferrybus/staten-island-ferry.shtml"),
        ("PHL", "https://www.nps.gov/inde/planyourvisit/libertybellcenter.htm"),
        ("DC", "https://www.wmata.com/pay.html"),
    ]:
        episode = (await client.post("/api/episodes", default_request(days=3, cities=[city])))["id"]
        for kind in ["mcp_discovery", "official_fetch"]:
            record = {
                "city": city,
                "kind": kind,
                "at": utcnow().isoformat(),
                "episode": episode,
                "actual_execution": True,
            }
            try:
                budget = Budget(store, episode, uid)
                if kind == "mcp_discovery":
                    results = await public_search(city, "hours", s, budget)
                    record.update(success=bool(results), result=results, promoted_to_verified=False)
                else:
                    content = await official_source(url, budget)
                    record.update(
                        success=bool(content),
                        url=url,
                        bytes=len(content),
                        sha256=hashlib.sha256(content).hexdigest(),
                        promoted_to_verified=False,
                    )
            except BaseException as exc:
                if isinstance(exc, (KeyboardInterrupt, asyncio.CancelledError)):
                    raise
                record.update(success=False, error=getattr(exc, "code", type(exc).__name__))
            append_record(out, record)
            print(city, kind, record["success"], record.get("error", ""), flush=True)
    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
