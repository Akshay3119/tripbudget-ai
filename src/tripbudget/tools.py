import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from .errors import DomainError
from .outbound import public_search_query, validate_url

READ_ONLY_TOOLS = frozenset({"catalog_options", "search_corpus", "public_search", "official_source"})


def authorize_tool(name):
    if name not in READ_ONLY_TOOLS:
        raise DomainError("TOOL_DENIED", "Tool is outside the read-only capability set", 403)


async def public_search(city, topic, settings, budget):
    try:
        return await _public_search(city, topic, settings, budget)
    except DomainError:
        raise
    except Exception:
        raise DomainError(
            "SEARCH_UNAVAILABLE", "MCP discovery unavailable; no source facts were changed", 503
        ) from None


async def _public_search(city, topic, settings, budget):
    authorize_tool("public_search")
    query = public_search_query(city, topic)
    await budget.external("searches")
    key = settings.tavily_api_key.get_secret_value()
    if not key:
        raise DomainError("SEARCH_UNAVAILABLE", "Tavily credential is not configured", 503)

    def client_factory(headers=None, timeout=None, auth=None):
        return httpx.AsyncClient(headers=headers, timeout=timeout, auth=auth, trust_env=False)

    async with streamablehttp_client(
        "https://mcp.tavily.com/mcp/",
        headers={"Authorization": "Bearer " + key},
        timeout=25,
        httpx_client_factory=client_factory,
    ) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            tool = next((t for t in listed.tools if t.name == "tavily_search"), None)
            if tool is None:
                raise DomainError(
                    "SEARCH_UNAVAILABLE", "Expected read-only search tool was not discovered", 503
                )
            result = await session.call_tool(
                tool.name,
                arguments={
                    "query": query,
                    "search_depth": "basic",
                    "max_results": 3,
                    "include_raw_content": False,
                },
            )
            if result.isError:
                raise DomainError("SEARCH_UNAVAILABLE", "MCP search reported a tool error", 503)
            data = [block.text for block in result.content if hasattr(block, "text")]
    # Tool result is untrusted discovery. It does not modify reviewed price facts.
    await budget.store.event(
        budget.episode,
        "mcp_search",
        {
            "tool": "tavily_search",
            "query": query,
            "result": data,
            "trusted": False,
        },
    )
    return data


async def official_source(url, budget):
    authorize_tool("official_source")
    validate_url(url)
    await budget.external("fetches")
    async with httpx.AsyncClient(trust_env=False, timeout=20, follow_redirects=False) as client:
        async with client.stream("GET", url) as response:
            if response.is_redirect:
                raise DomainError("OUTBOUND_DENIED", "Redirects require a new registered source", 403)
            response.raise_for_status()
            parts, size = [], 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > 2_000_000:
                    raise DomainError("RESOURCE_LIMIT", "Source page exceeds two megabytes")
                parts.append(chunk)
    return b"".join(parts)
