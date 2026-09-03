# Copyright 2026 Shopware × Claude Commerce Agents authors.
# SPDX-License-Identifier: Apache-2.0

"""Every fixture here runs over ``replay_transport`` — Shopware-shaped responses, never the live shop."""

from __future__ import annotations

import os

os.environ.setdefault("CATALOG_WARMUP", "0")
os.environ.setdefault("SHOPWARE_URL", "http://shopware.test")
os.environ.setdefault("SHOPWARE_SALES_CHANNEL_ACCESS_KEY", "test-key")
os.environ.setdefault("UCP_AGENT_PROFILE_URL", "http://shopware.test/.well-known/ucp")
os.environ.setdefault("UCP_TRANSPORT", "rest")
os.environ.setdefault("SHOPWARE_AGENT_COMPLETE_CHECKOUT", "0")

import httpx
import pytest

from shopping_agent import ShoppingSessionContext, ShoppingSessionState
from storefront.api.shopware_backend import ShopwareStorefrontBackend
from storefront.api.store_api import StoreApiClient
from storefront.api.ucp_client import UcpClient

from .replay import SEARCH_QUERY, replay_transport

__all__ = ["SEARCH_QUERY"]


@pytest.fixture
def transport() -> httpx.MockTransport:
    return replay_transport()


@pytest.fixture
def client(transport: httpx.MockTransport) -> UcpClient:
    return UcpClient(
        shop_url="http://shopware.test",
        http=httpx.AsyncClient(transport=transport),
        retry_backoff=0.0,
        transport="rest",
    )


@pytest.fixture
def store_api(transport: httpx.MockTransport) -> StoreApiClient:
    return StoreApiClient(
        "http://shopware.test",
        access_key="test-key",
        http=httpx.AsyncClient(transport=transport),
    )


@pytest.fixture
def backend(client: UcpClient, store_api: StoreApiClient) -> ShopwareStorefrontBackend:
    return ShopwareStorefrontBackend(client, store_api=store_api, store_name="Shopware")


@pytest.fixture
def session() -> ShoppingSessionContext:
    return ShoppingSessionContext(session_id="s-1", user_id="guest")


@pytest.fixture
def state() -> ShoppingSessionState:
    return ShoppingSessionState()
