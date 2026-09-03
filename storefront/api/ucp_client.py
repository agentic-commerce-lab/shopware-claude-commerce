# Copyright 2026 Shopware × Claude Commerce Agents authors.
# SPDX-License-Identifier: Apache-2.0

"""UCP client for a Shopware sales channel.

Two transports, same documents:

* **REST** (default) ``/ucp/v1/*`` — catalog.search/lookup, carts, checkout-sessions.
  This is the path Shopware's functional suite drives and the one this host uses
  first. Writes send ``Idempotency-Key``. Every runtime call sends ``UCP-Agent``.
* **MCP** ``POST /ucp/mcp`` — Shopware tool names (``shopware-ucp-catalog-search``,
  …). Mutating tools default to ``dryRun=true`` on the server; this client always
  sends ``dryRun=false`` for real cart/checkout writes.

``signature-policy=log`` (local) accepts unsigned requests. A PEM at
``UCP_AGENT_SIGNING_KEY_PEM_FILE`` is reserved for RFC 9421 when policy is
``strict``; local compose does not require it.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from typing import Any
from urllib.parse import urlparse

import httpx

DEFAULT_SHOP_URL = "http://localhost:8080"
_TIMEOUT = httpx.Timeout(25.0)
_TRANSIENT = {429, 500, 502, 503, 504}
_CART_GONE = {"cart_not_found", "invalid_cart_id"}

# Shopware Store API MCP tool names behind /ucp/mcp (see docs/shopware-mapping.md).
MCP_TOOLS = {
    "search_catalog": "shopware-ucp-catalog-search",
    "lookup_catalog": "shopware-ucp-catalog-lookup",
    "get_product": "shopware-ucp-catalog-lookup",
    "create_cart": "shopware-ucp-cart-create",
    "update_cart": "shopware-ucp-cart-update",
    "get_cart": "shopware-ucp-cart-get",
    "cancel_cart": "shopware-ucp-cart-cancel",
    "create_checkout": "shopware-ucp-checkout-create",
    "update_checkout": "shopware-ucp-checkout-update",
    "get_checkout": "shopware-ucp-checkout-get",
    "complete_checkout": "shopware-ucp-checkout-complete",
    "cancel_checkout": "shopware-ucp-checkout-cancel",
    "get_order": "shopware-ucp-order-get",
}

_MUTATING = {
    "create_cart",
    "update_cart",
    "cancel_cart",
    "create_checkout",
    "update_checkout",
    "complete_checkout",
    "cancel_checkout",
}


def shop_url_from_env() -> str:
    return os.environ.get("SHOPWARE_URL", DEFAULT_SHOP_URL).rstrip("/")


def profile_url_from_env(shop_url: str | None = None) -> str:
    explicit = os.environ.get("UCP_AGENT_PROFILE_URL")
    if explicit:
        return explicit
    # Shopware fetches this URL from inside Docker. The published host port
    # (localhost:8080) is unreachable from the container; Apache listens on :80.
    # Bootstrap / compose publish agent-profile.json at that path. The allowlist
    # host is `localhost` (APP_URL), not 127.0.0.1 unless both are configured.
    return "http://localhost/agent-profile.json"


def transport_from_env() -> str:
    value = os.environ.get("UCP_TRANSPORT", "rest").strip().lower()
    return value if value in {"rest", "mcp"} else "rest"


class UcpError(RuntimeError):
    def __init__(self, message: str, codes: frozenset[str] = frozenset()) -> None:
        super().__init__(message)
        self.codes = codes


class UcpAuthError(UcpError):
    """Buyer token rejected (401)."""


class UcpCartGoneError(UcpError):
    """The shop no longer accepts this cart id."""


class UcpClient:
    def __init__(
        self,
        shop_url: str | None = None,
        profile_url: str | None = None,
        http: httpx.AsyncClient | None = None,
        retry_backoff: float = 0.5,
        transport: str | None = None,
    ) -> None:
        self.shop_url = (shop_url or shop_url_from_env()).rstrip("/")
        self.discovery_url = f"{self.shop_url}/.well-known/ucp"
        self.mcp_url = f"{self.shop_url}/ucp/mcp"
        self.rest_prefix = f"{self.shop_url}/ucp/v1"
        self._profile_url = profile_url or profile_url_from_env(self.shop_url)
        self._http = http or httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True)
        self._retry_backoff = retry_backoff
        self._next_id = 0
        self.transport = transport or transport_from_env()

    async def aclose(self) -> None:
        await self._http.aclose()

    def _agent_header(self) -> str:
        return f'platform; profile="{self._profile_url}"'

    def _headers(self, *, write: bool = False) -> dict[str, str]:
        headers = {
            "Accept": "application/json, text/event-stream",
            "UCP-Agent": self._agent_header(),
        }
        if write:
            headers["Content-Type"] = "application/json"
            headers["Idempotency-Key"] = str(uuid.uuid4())
        return headers

    async def discover(self) -> dict[str, Any]:
        response = await self._http.get(self.discovery_url, headers={"Accept": "application/json"})
        response.raise_for_status()
        return response.json()

    async def call_ucp(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        bearer_token: str | None = None,
        buyer_ip: str | None = None,
        document_error_ok: bool = False,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Catalog / cart / checkout / order. REST is the default; MCP when
        ``UCP_TRANSPORT=mcp`` or REST is unavailable for this operation."""
        if self.transport == "mcp":
            return await self._call_mcp(
                name,
                arguments,
                bearer_token=bearer_token,
                document_error_ok=document_error_ok,
                dry_run=dry_run,
            )
        try:
            return await self._call_rest(
                name,
                arguments,
                bearer_token=bearer_token,
                document_error_ok=document_error_ok,
            )
        except httpx.HTTPStatusError as error:
            if error.response.status_code in {404, 405}:
                return await self._call_mcp(
                    name,
                    arguments,
                    bearer_token=bearer_token,
                    document_error_ok=document_error_ok,
                    dry_run=dry_run,
                )
            raise

    async def _call_rest(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        bearer_token: str | None,
        document_error_ok: bool,
    ) -> dict[str, Any]:
        method, path, body = _rest_request(name, arguments)
        url = f"{self.rest_prefix}{path}"
        write = method in {"POST", "PATCH", "PUT", "DELETE"} and body is not None
        headers = self._headers(write=write)
        if bearer_token:
            headers["Authorization"] = f"Bearer {bearer_token}"
        response = await self._request(method, url, headers=headers, json=body)
        if response.status_code == 401:
            raise UcpAuthError(f"{name}: UCP rejected the token (401)")
        if response.status_code in {404, 405} and not _has_ucp_messages(response):
            response.raise_for_status()
        if response.status_code >= 400:
            raise _http_error(name, response)
        payload = _json_payload(response)
        return _maybe_document_error(name, payload, document_error_ok=document_error_ok)

    async def _call_mcp(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        bearer_token: str | None,
        document_error_ok: bool,
        dry_run: bool,
    ) -> dict[str, Any]:
        tool = MCP_TOOLS.get(name, name)
        params = _mcp_arguments(name, arguments, dry_run=dry_run)
        self._next_id += 1
        body = {
            "jsonrpc": "2.0",
            "id": self._next_id,
            "method": "tools/call",
            "params": {
                "name": tool,
                "arguments": {
                    "meta": {"ucp-agent": {"profile": self._profile_url}},
                    **params,
                },
            },
        }
        headers = self._headers(write=True)
        if bearer_token:
            headers["Authorization"] = f"Bearer {bearer_token}"
        response = await self._request("POST", self.mcp_url, headers=headers, json=body)
        if response.status_code == 401:
            raise UcpAuthError(f"{name}: UCP rejected the token (401)")
        response.raise_for_status()
        return _tool_payload(_rpc_body(response), name, document_error_ok=document_error_ok)

    async def _request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any] | None,
    ) -> httpx.Response:
        response = await self._http.request(method, url, headers=headers, json=json)
        if response.status_code in _TRANSIENT:
            await asyncio.sleep(self._retry_backoff)
            response = await self._http.request(method, url, headers=headers, json=json)
        return response


def _rest_request(name: str, arguments: dict[str, Any]) -> tuple[str, str, dict[str, Any] | None]:
    catalog = arguments.get("catalog") or {}
    if name == "search_catalog":
        body: dict[str, Any] = {
            "query": catalog.get("query") or arguments.get("query") or "",
            "limit": (catalog.get("pagination") or {}).get("limit")
            or arguments.get("limit")
            or 8,
        }
        if catalog.get("filters"):
            body["filters"] = catalog["filters"]
        if arguments.get("filters"):
            body["filters"] = arguments["filters"]
        return "POST", "/catalog/search", body
    if name in {"lookup_catalog", "get_product"}:
        ids = catalog.get("ids") or arguments.get("ids")
        product_id = catalog.get("id") or arguments.get("id")
        if name == "get_product" and product_id and not ids:
            return "GET", f"/catalog/product/{product_id}", None
        return "POST", "/catalog/lookup", {"ids": ids or ([product_id] if product_id else [])}
    if name == "create_cart":
        return "POST", "/carts", arguments.get("cart") or arguments
    if name == "get_cart":
        return "GET", f"/carts/{arguments['id']}", None
    if name == "update_cart":
        cart = arguments.get("cart") or arguments
        cart_id = arguments.get("id") or cart.get("id")
        return "PATCH", f"/carts/{cart_id}", {"id": cart_id, **{k: v for k, v in cart.items() if k != "id"}}
    if name == "cancel_cart":
        return "POST", f"/carts/{arguments['id']}/cancel", {}
    if name == "create_checkout":
        return "POST", "/checkout-sessions", arguments.get("checkout") or arguments
    if name == "get_checkout":
        return "GET", f"/checkout-sessions/{arguments['id']}", None
    if name == "update_checkout":
        checkout = arguments.get("checkout") or arguments
        checkout_id = arguments.get("id") or checkout.get("id")
        return "PATCH", f"/checkout-sessions/{checkout_id}", {
            "id": checkout_id,
            **{k: v for k, v in checkout.items() if k != "id"},
        }
    if name == "complete_checkout":
        return "POST", f"/checkout-sessions/{arguments['id']}/complete", arguments
    if name == "get_order":
        return "GET", f"/orders/{arguments['id']}", None
    raise UcpError(f"Unknown UCP operation {name!r}")


def _mcp_arguments(name: str, arguments: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    catalog = arguments.get("catalog") or {}
    if name == "search_catalog":
        return {
            "query": catalog.get("query") or arguments.get("query") or "",
            "limit": (catalog.get("pagination") or {}).get("limit") or arguments.get("limit") or 8,
        }
    if name in {"lookup_catalog", "get_product"}:
        ids = catalog.get("ids") or arguments.get("ids")
        product_id = catalog.get("id") or arguments.get("id")
        payload = ids or ([product_id] if product_id else [])
        return {"ids": json.dumps(payload)}
    if name == "get_cart":
        return {"id": arguments["id"]}
    if name == "get_checkout":
        return {"id": arguments["id"]}
    if name == "get_order":
        return {"id": arguments["id"]}
    if name in _MUTATING:
        if name == "update_cart":
            cart = arguments.get("cart") or {}
            payload = {"id": arguments.get("id"), "line_items": cart.get("line_items") or []}
            return {
                "id": arguments["id"],
                "payload": json.dumps(payload),
                "dryRun": dry_run,
            }
        if name == "update_checkout":
            checkout = arguments.get("checkout") or arguments
            return {
                "id": arguments["id"],
                "payload": json.dumps(checkout),
                "dryRun": dry_run,
            }
        body = arguments.get("cart") or arguments.get("checkout") or arguments
        return {"payload": json.dumps(body), "dryRun": dry_run}
    return arguments


def _has_ucp_messages(response: httpx.Response) -> bool:
    try:
        payload = response.json()
    except ValueError:
        return False
    return isinstance(payload, dict) and bool(payload.get("messages"))


def _json_payload(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError as error:
        raise UcpError(f"Non-JSON UCP response ({response.status_code})") from error
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        return {"results": data}
    return {"text": str(data)}


def _http_error(name: str, response: httpx.Response) -> UcpError:
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    messages = payload.get("messages") or []
    contents = [m.get("content", "") for m in messages if isinstance(m, dict)]
    text = "; ".join(c for c in contents if c) or payload.get("detail") or response.text[:400]
    codes = frozenset(
        m.get("code") for m in messages if isinstance(m, dict) and m.get("code")
    )
    cls = UcpCartGoneError if codes & _CART_GONE or "cart_not_found" in text else UcpError
    return cls(f"{name}: {text or response.status_code}", codes)


def _maybe_document_error(
    name: str, payload: dict[str, Any], *, document_error_ok: bool
) -> dict[str, Any]:
    messages = payload.get("messages") or []
    is_error = payload.get("isError") or any(
        isinstance(m, dict) and m.get("type") == "error" for m in messages
    )
    if is_error and not (document_error_ok and payload.get("id")):
        raise _http_error(name, httpx.Response(422, json=payload))
    return payload


def _rpc_body(response: httpx.Response) -> dict[str, Any]:
    content_type = response.headers.get("content-type", "")
    if "text/event-stream" not in content_type:
        return response.json()
    for line in response.text.splitlines():
        if line.startswith("data:"):
            return json.loads(line[len("data:") :].strip())
    raise UcpError("Empty event stream from the MCP endpoint.")


def _tool_payload(body: dict[str, Any], name: str, *, document_error_ok: bool) -> dict[str, Any]:
    if "error" in body:
        error = body["error"]
        raise UcpError(f"{name}: {error.get('message', 'JSON-RPC error')}")
    result = body.get("result") or {}
    texts = [
        block.get("text", "")
        for block in result.get("content") or []
        if isinstance(block, dict)
    ]
    payload = result.get("structuredContent")
    if not isinstance(payload, dict):
        payload = None
        for text in texts:
            try:
                parsed = json.loads(text)
            except (TypeError, ValueError):
                continue
            if isinstance(parsed, dict):
                payload = parsed
                break
            if isinstance(parsed, list):
                payload = {"results": parsed}
                break
    if result.get("isError") and not (document_error_ok and payload and payload.get("id")):
        joined = " ".join(texts)
        raise UcpError(f"{name}: {joined or 'tool error'}")
    return payload if payload is not None else {"text": "\n".join(texts)}


def origin_host(url: str) -> str:
    return urlparse(url).hostname or "localhost"
