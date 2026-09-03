# Copyright 2026 Shopware × Claude Commerce Agents authors.
# SPDX-License-Identifier: Apache-2.0

"""Store API client for surfaces UCP does not cover: context/branding, CMS policies,
shipping methods, product associations (variants, Grundpreis, deliveryTime)."""

from __future__ import annotations

import os
from typing import Any

import httpx

_TIMEOUT = httpx.Timeout(20.0)


def access_key_from_env() -> str:
    return os.environ.get("SHOPWARE_SALES_CHANNEL_ACCESS_KEY", "")


class StoreApiClient:
    def __init__(
        self,
        shop_url: str,
        access_key: str | None = None,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self.shop_url = shop_url.rstrip("/")
        self.access_key = access_key if access_key is not None else access_key_from_env()
        self._http = http or httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True)

    @property
    def configured(self) -> bool:
        return bool(self.access_key)

    def _headers(self, context_token: str | None = None) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "sw-access-key": self.access_key,
        }
        if context_token:
            headers["sw-context-token"] = context_token
        return headers

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        context_token: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        if not self.configured:
            return None
        response = await self._http.request(
            method,
            f"{self.shop_url}{path}",
            headers=self._headers(context_token),
            json=json,
            params=params,
        )
        if response.status_code >= 400:
            return None
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError:
            return {"text": response.text}

    async def context(self) -> dict[str, Any]:
        return await self._request("GET", "/store-api/context") or {}

    async def search_products(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        body = await self._request(
            "POST",
            "/store-api/search",
            json={"limit": limit, "associations": _product_associations()},
            params={"search": query},
        )
        if not body:
            return []
        return body.get("elements") or body.get("products") or []

    async def product(self, product_id: str) -> dict[str, Any] | None:
        body = await self._request(
            "POST",
            f"/store-api/product/{product_id}",
            json={"associations": _product_associations()},
        )
        if not body:
            return None
        return body.get("product") or body.get("data") or body

    async def child_products(self, parent_id: str) -> list[dict[str, Any]]:
        """Variants of a parent. Product detail often returns the selected child, not children[]."""
        body = await self._request(
            "POST",
            "/store-api/product",
            json={
                "limit": 50,
                "filter": [{"type": "equals", "field": "parentId", "value": parent_id}],
                "associations": {
                    "options": {"associations": {"group": {}}},
                    "cover": {"associations": {"media": {}}},
                },
            },
        )
        if not body:
            return []
        return body.get("elements") or body.get("products") or []

    async def shipping_methods(self, context_token: str | None = None) -> list[dict[str, Any]]:
        body = await self._request(
            "POST",
            "/store-api/shipping-method",
            json={},
            params={"onlyAvailable": 1},
            context_token=context_token,
        )
        if not body:
            return []
        return body.get("elements") or []

    async def navigation(self, name: str = "footer-navigation") -> list[dict[str, Any]]:
        body = await self._request("GET", f"/store-api/navigation/{name}/{name}")
        if isinstance(body, list):
            return body
        if isinstance(body, dict):
            return body.get("elements") or []
        return []

    async def category(self, category_id: str) -> dict[str, Any]:
        return await self._request("POST", f"/store-api/category/{category_id}", json={}) or {}

    async def text_file(self, path: str) -> str:
        response = await self._http.get(f"{self.shop_url}{path}", follow_redirects=True)
        if response.status_code >= 400:
            return ""
        return response.text


def _product_associations() -> dict[str, Any]:
    return {
        "children": {
            "associations": {
                "options": {"associations": {"group": {}}},
                "cover": {"associations": {"media": {}}},
            }
        },
        "options": {"associations": {"group": {}}},
        "properties": {"associations": {"group": {}}},
        "cover": {"associations": {"media": {}}},
        "deliveryTime": {},
        "unit": {},
        "manufacturer": {},
        "categories": {},
        "seoUrls": {},
    }
