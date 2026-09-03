# Copyright 2026 Shopware × Claude Commerce Agents authors.
# SPDX-License-Identifier: Apache-2.0

"""The wired storefront app, on routes that reach no network."""

from __future__ import annotations

import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from demo_common import SESSION_HEADER
from shopping_agent import ShoppingSessionContext
from shopping_agent.types import ProductDetails
from storefront.api import main as main_module
from storefront.api.store_api import StoreApiClient
from storefront.api.ucp_client import UcpClient

from .replay import GONE_CART_ID, PRODUCT_ID, replay_transport


@pytest.fixture
def client():
    return TestClient(main_module.app, base_url="http://localhost")


def start(client: TestClient) -> dict[str, str]:
    token = client.post("/api/session", json={"user_id": "guest"}).json()["session_id"]
    return {SESSION_HEADER: token}


def _bind_replay(monkeypatch, transport: httpx.MockTransport | None = None) -> httpx.MockTransport:
    transport = transport or replay_transport()
    monkeypatch.setattr(
        main_module.backend,
        "client",
        UcpClient(
            shop_url="http://shopware.test",
            http=httpx.AsyncClient(transport=transport),
            retry_backoff=0.0,
        ),
    )
    monkeypatch.setattr(
        main_module.backend,
        "store_api",
        StoreApiClient(
            "http://shopware.test",
            access_key="test-key",
            http=httpx.AsyncClient(transport=transport),
        ),
    )
    return transport


def test_health_and_session(client):
    health = client.get("/api/health").json()
    assert health["ok"] is True
    assert health["store"] == "Shopware"
    assert start(client)


def test_the_catalog_detail_route_takes_a_hex_id(client):
    product = ProductDetails(product_id=PRODUCT_ID, title="Fake Shirt", price=29.99, currency="EUR")
    main_module.backend.products[PRODUCT_ID] = product
    try:
        response = client.get(f"/api/products/{PRODUCT_ID}")
        assert response.status_code == 200
        assert response.json()["product_id"] == PRODUCT_ID
        assert client.get("/api/products/ffffffffffffffffffffffffffffffff").status_code == 404
    finally:
        main_module.backend.products.pop(PRODUCT_ID, None)


def test_a_fresh_session_has_an_empty_cart_and_no_checkout_url(client):
    payload = client.get("/api/cart", headers=start(client)).json()
    assert payload["items"] == []
    assert payload["checkout_url"] is None


def test_the_cart_payload_carries_the_backends_staged_handoff_url(client, monkeypatch):
    headers = start(client)
    sid = headers[SESSION_HEADER]

    async def staged(session_id):
        assert session_id == sid
        return "http://localhost:8080/checkout/confirm?checkoutId=abc"

    monkeypatch.setattr(main_module.backend, "checkout_url_for", staged)
    payload = client.get("/api/cart", headers=headers).json()
    assert payload["checkout_url"] == "http://localhost:8080/checkout/confirm?checkoutId=abc"


def test_the_direct_add_button_holds_without_provenance(client, monkeypatch):
    _bind_replay(monkeypatch)
    response = client.post(
        "/api/cart/add",
        json={"product_id": PRODUCT_ID, "quantity": 1},
        headers=start(client),
    )
    assert response.status_code == 400


def test_the_direct_add_button_works_for_a_product_already_on_the_grid(client, monkeypatch):
    _bind_replay(monkeypatch)
    product = ProductDetails(product_id=PRODUCT_ID, title="Claude Commerce T-Shirt", price=29.99, currency="EUR")
    main_module.backend.products[PRODUCT_ID] = product
    try:
        response = client.post(
            "/api/cart/add",
            json={"product_id": PRODUCT_ID, "quantity": 1},
            headers=start(client),
        )
        assert response.status_code == 200, response.text
        assert response.json()["cart"]["item_count"] >= 1
        assert response.json().get("checkout_url")
    finally:
        main_module.backend.products.pop(PRODUCT_ID, None)


def test_attach_binds_the_session_to_a_shopware_cart(client, monkeypatch):
    _bind_replay(monkeypatch)
    headers = start(client)
    assert client.get("/api/cart", headers=headers).json()["cart_id"] is None

    async def seed() -> str:
        session = ShoppingSessionContext(session_id="attach-seed", user_id="guest")
        await main_module.backend.search_products(session, "shirt", limit=1)
        await main_module.backend.add_to_cart(session, PRODUCT_ID, 1)
        cart_id = main_module.backend.cart_id_for("attach-seed")
        assert cart_id
        return cart_id

    cart_id = asyncio.run(seed())
    attached = client.post("/api/cart/attach", json={"cart_id": cart_id}, headers=headers)
    assert attached.status_code == 200
    assert attached.json()["item_count"] == 1
    assert attached.json()["cart_id"] == cart_id

    unknown = client.post("/api/cart/attach", json={"cart_id": GONE_CART_ID}, headers=headers)
    assert unknown.status_code == 404
    assert client.get("/api/cart", headers=headers).json()["cart_id"] == cart_id


def test_a_fresh_session_is_signed_out(client):
    assert client.get("/api/auth/status", headers=start(client)).json() == {"signed_in": False}


def test_signin_start_requires_a_session(client):
    assert client.get("/api/auth/shopware/start", follow_redirects=False).status_code == 401


def test_signin_start_without_credentials_says_whats_missing(client, monkeypatch):
    monkeypatch.delenv("SHOPWARE_UCP_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("SHOPWARE_UCP_OAUTH_CLIENT_SECRET", raising=False)
    response = client.get(
        "/api/auth/shopware/start",
        params={"session_id": start(client)[SESSION_HEADER]},
        follow_redirects=False,
    )
    assert response.status_code == 503
    assert "SHOPWARE_UCP_OAUTH_CLIENT_ID" in response.json()["detail"]
