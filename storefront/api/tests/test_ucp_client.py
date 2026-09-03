# Copyright 2026 Shopware × Claude Commerce Agents authors.
# SPDX-License-Identifier: Apache-2.0

"""UCP REST client: agent header, idempotency, retry, cart-gone, MCP fallback."""

from __future__ import annotations

import json

import httpx
import pytest

from storefront.api.ucp_client import MCP_TOOLS, UcpCartGoneError, UcpClient, UcpError


def capture_client(*responses: httpx.Response, transport: str = "rest") -> tuple[UcpClient, list[httpx.Request]]:
    requests: list[httpx.Request] = []
    queue = list(responses)

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return queue.pop(0) if len(queue) > 1 else queue[0]

    client = UcpClient(
        shop_url="http://shopware.test",
        http=httpx.AsyncClient(transport=httpx.MockTransport(handle)),
        retry_backoff=0.0,
        transport=transport,
    )
    return client, requests


async def test_rest_search_sends_ucp_agent_header_and_profile():
    client, requests = capture_client(httpx.Response(200, json={"products": []}))
    await client.call_ucp("search_catalog", {"catalog": {"query": "shirt"}})
    headers = requests[0].headers
    assert headers["ucp-agent"] == 'platform; profile="http://shopware.test/.well-known/ucp"'
    body = json.loads(requests[0].content)
    assert body["query"] == "shirt"
    assert str(requests[0].url).endswith("/ucp/v1/catalog/search")


async def test_cart_create_sends_idempotency_key():
    client, requests = capture_client(
        httpx.Response(201, json={"id": "c1", "line_items": []})
    )
    await client.call_ucp("create_cart", {"cart": {"line_items": []}})
    assert requests[0].headers.get("idempotency-key")
    assert requests[0].method == "POST"


async def test_a_transient_status_is_retried_once():
    ok = httpx.Response(200, json={"products": []})
    client, requests = capture_client(httpx.Response(429, json={}), ok)
    assert await client.call_ucp("search_catalog", {"catalog": {"query": "x"}}) == {"products": []}
    assert len(requests) == 2


async def test_cart_gone_code_raises_recoverable_subclass():
    client, _ = capture_client(
        httpx.Response(
            404,
            json={
                "messages": [
                    {"type": "error", "code": "cart_not_found", "content": "The requested cart is gone"}
                ]
            },
        )
    )
    with pytest.raises(UcpCartGoneError, match="gone"):
        await client.call_ucp("get_cart", {"id": "00000000000000000000000000000000"})


async def test_rest_404_falls_back_to_mcp():
    rest_miss = httpx.Response(404, json={"detail": "no rest"})
    mcp_hit = httpx.Response(
        200,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"structuredContent": {"products": [{"id": "1"}]}},
        },
    )
    client, requests = capture_client(rest_miss, mcp_hit)
    payload = await client.call_ucp("search_catalog", {"catalog": {"query": "shirt"}})
    assert payload == {"products": [{"id": "1"}]}
    assert str(requests[0].url).endswith("/ucp/v1/catalog/search")
    assert str(requests[1].url).endswith("/ucp/mcp")
    mcp_body = json.loads(requests[1].content)
    assert mcp_body["params"]["name"] == MCP_TOOLS["search_catalog"]


async def test_mcp_writes_send_dry_run_false():
    client, requests = capture_client(
        httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {"structuredContent": {"id": "c1"}}}),
        transport="mcp",
    )
    await client.call_ucp("create_cart", {"cart": {"line_items": []}})
    arguments = json.loads(requests[0].content)["params"]["arguments"]
    assert arguments["dryRun"] is False
    assert arguments["meta"]["ucp-agent"]["profile"].endswith("/.well-known/ucp")


async def test_jsonrpc_error_raises():
    client, _ = capture_client(
        httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message": "nope"}},
        ),
        transport="mcp",
    )
    with pytest.raises(UcpError, match="nope"):
        await client.call_ucp("search_catalog", {"catalog": {"query": "x"}})
