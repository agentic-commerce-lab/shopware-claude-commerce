# Copyright 2026 Shopware × Claude Commerce Agents authors.
# SPDX-License-Identifier: Apache-2.0

"""Shopware Admin REST client. Password grant (administration) or integration
client_credentials. Every mutating call is recorded on ``calls`` so tests can prove
staging never writes. Optional ``dry_run`` skips the PATCH and returns the payload
that would have been sent (Admin MCP ``dryRun=true`` when ``SHOPWARE_ADMIN_TRANSPORT=mcp``).
"""

from __future__ import annotations

import os
import time
from typing import Any, Protocol

import httpx

EUR_CURRENCY_ID = "b7d2554b0ce847cd82f3ac9bd1c0dfca"
_TIMEOUT = httpx.Timeout(30.0)


class AdminAPIError(RuntimeError):
    pass


class AdminTransport(Protocol):
    calls: list[tuple[str, str, dict[str, Any]]]

    async def search(self, entity: str, body: dict[str, Any]) -> dict[str, Any]: ...

    async def get(self, entity: str, entity_id: str) -> dict[str, Any]: ...

    async def patch(
        self, entity: str, entity_id: str, payload: dict[str, Any], *, dry_run: bool = False
    ) -> dict[str, Any]: ...

    async def aclose(self) -> None: ...


class AdminClient:
    def __init__(
        self,
        shop_url: str,
        *,
        username: str = "",
        password: str = "",
        access_key: str = "",
        secret_key: str = "",
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self.shop_url = shop_url.rstrip("/")
        self._username = username
        self._password = password
        self._access_key = access_key
        self._secret_key = secret_key
        self._http = http or httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True)
        self._token: str | None = None
        self._token_exp = 0.0
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _ensure_token(self) -> str:
        if self._token and time.time() < self._token_exp - 30:
            return self._token
        if self._access_key and self._secret_key:
            body = {
                "grant_type": "client_credentials",
                "client_id": self._access_key,
                "client_secret": self._secret_key,
            }
        else:
            body = {
                "grant_type": "password",
                "client_id": "administration",
                "username": self._username,
                "password": self._password,
            }
        response = await self._http.post(f"{self.shop_url}/api/oauth/token", json=body)
        if response.status_code >= 400:
            raise AdminAPIError(f"oauth token failed: {response.status_code} {response.text[:400]}")
        payload = response.json()
        self._token = payload["access_token"]
        self._token_exp = time.time() + int(payload.get("expires_in") or 600)
        return self._token

    def _headers(self, token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def search(self, entity: str, body: dict[str, Any]) -> dict[str, Any]:
        token = await self._ensure_token()
        response = await self._http.post(
            f"{self.shop_url}/api/search/{entity}",
            headers=self._headers(token),
            json=body,
        )
        if response.status_code >= 400:
            raise AdminAPIError(f"search {entity}: {response.status_code} {response.text[:400]}")
        return response.json()

    async def get(self, entity: str, entity_id: str) -> dict[str, Any]:
        token = await self._ensure_token()
        response = await self._http.get(
            f"{self.shop_url}/api/{entity}/{entity_id}",
            headers=self._headers(token),
        )
        if response.status_code >= 400:
            raise AdminAPIError(f"get {entity}/{entity_id}: {response.status_code}")
        return response.json()

    async def patch(
        self, entity: str, entity_id: str, payload: dict[str, Any], *, dry_run: bool = False
    ) -> dict[str, Any]:
        self.calls.append(("PATCH", f"{entity}/{entity_id}", payload))
        if dry_run:
            return {"dryRun": True, "payload": payload}
        if os.environ.get("SHOPWARE_ADMIN_TRANSPORT", "rest") == "mcp":
            preview = await self._mcp_upsert(entity, entity_id, payload, dry_run=True)
            if preview is not None:
                return preview
        token = await self._ensure_token()
        response = await self._http.patch(
            f"{self.shop_url}/api/{entity}/{entity_id}",
            headers=self._headers(token),
            json=payload,
        )
        if response.status_code >= 400:
            raise AdminAPIError(
                f"patch {entity}/{entity_id}: {response.status_code} {response.text[:400]}"
            )
        if not response.content:
            return {"id": entity_id}
        return response.json()

    async def _mcp_upsert(
        self, entity: str, entity_id: str, payload: dict[str, Any], *, dry_run: bool
    ) -> dict[str, Any] | None:
        try:
            token = await self._ensure_token()
            body = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "shopware-entity-upsert",
                    "arguments": {
                        "entity": entity,
                        "payload": {**payload, "id": entity_id},
                        "dryRun": dry_run,
                    },
                },
            }
            response = await self._http.post(
                f"{self.shop_url}/api/_mcp",
                headers=self._headers(token),
                json=body,
            )
            if response.status_code >= 400:
                return None
            return response.json()
        except Exception:
            return None
