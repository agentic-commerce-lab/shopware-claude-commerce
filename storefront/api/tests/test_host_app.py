# Copyright 2026 shopware AG
# SPDX-License-Identifier: MIT

"""The wired storefront app, on routes that reach no network: the grid's add button (details
first, then the gated add), cart attach, the click-time handoff page, identity linking."""

from __future__ import annotations

import asyncio
import re
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi.testclient import TestClient

from demo_common import SESSION_HEADER
from shopping_agent import ShoppingSessionContext
from shopping_agent.types import ProductDetails
from shopware_common.handoff import HandoffCodeVerifier
from shopware_common.http_signing import RequestSigner
from storefront.api import main as main_module
from storefront.api.identity import ShopwareIdentityLinking
from storefront.api.store_api import StoreApiClient
from storefront.api.ucp_client import UcpClient

from .conftest import HANDOFF_SECRET
from .replay import (
    CART_ID,
    CUSTOMER_EMAIL,
    CUSTOMER_PASSWORD,
    CUSTOMER_TOKEN,
    GONE_CART_ID,
    MAIN_ID,
    PRODUCT_ID,
    VARIANT_S,
    ShopwareReplay,
)


@pytest.fixture
def client():
    return TestClient(main_module.app, base_url="http://localhost")


def start(client: TestClient) -> dict[str, str]:
    token = client.post("/api/session", json={"user_id": "guest"}).json()["session_id"]
    return {SESSION_HEADER: token}


def _bind_replay(
    monkeypatch, shop: ShopwareReplay | None = None, signer: RequestSigner | None = None
) -> ShopwareReplay:
    shop = shop or ShopwareReplay(public_key=signer.public_key if signer else None)
    transport = httpx.MockTransport(shop.handle)
    ucp = UcpClient(
        shop_url="http://shopware.test",
        http=httpx.AsyncClient(transport=transport),
        retry_backoff=0.0,
        transport="mcp",
        signer=signer,
    )
    store = StoreApiClient(
        "http://shopware.test", access_key="test-key", http=httpx.AsyncClient(transport=transport)
    )
    monkeypatch.setattr(main_module.backend, "client", ucp)
    monkeypatch.setattr(main_module.backend, "store_api", store)
    monkeypatch.setattr(main_module.backend.policies, "_store_api", store)
    monkeypatch.setattr(
        main_module.backend.handoff,
        "_issuer",
        main_module.HandoffBroker(
            "http://shopware.test", public_url="http://host.test", secret=HANDOFF_SECRET
        )._issuer,
    )
    monkeypatch.setattr(main_module.backend.handoff, "public_url", "http://host.test")
    monkeypatch.setattr(main_module.backend.handoff, "shop_url", "http://shopware.test")
    return shop


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
    assert payload["cart_id"] is None


def test_the_add_button_reads_details_first_so_a_variant_enters_provenance(client, monkeypatch):
    _bind_replay(monkeypatch)
    headers = start(client)
    response = client.post(
        "/api/cart/add", json={"product_id": VARIANT_S, "quantity": 1}, headers=headers
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["cart"]["item_count"] == 1
    assert body["cart_id"] == CART_ID
    assert body["checkout_url"].startswith("http://host.test/api/checkout/handoff/")
    record = main_module.host.sessions.require(headers[SESSION_HEADER])
    assert record.state.seen_products[VARIANT_S].variant_of == PRODUCT_ID


def test_the_add_button_runs_under_the_customers_clock(client, monkeypatch):
    """``shopping_context`` gives the executor an aware ``now`` in the browser's zone
    (``X-Timezone``), else ``HOST_TIMEZONE``; never the server's naive wall clock."""
    _bind_replay(monkeypatch)
    monkeypatch.setenv("HOST_TIMEZONE", "Europe/Berlin")
    seen: list[ShoppingSessionContext] = []
    real_executor_class = main_module.agent.executor_class

    def spying_executor(**kwargs):
        seen.append(kwargs["session"])
        return real_executor_class(**kwargs)

    monkeypatch.setattr(main_module.agent, "executor_class", spying_executor)
    headers = start(client)
    client.post(
        "/api/cart/add",
        json={"product_id": VARIANT_S, "quantity": 1},
        headers={**headers, "X-Timezone": "America/Chicago"},
    )
    client.post("/api/cart/add", json={"product_id": VARIANT_S, "quantity": 1}, headers=headers)
    # Each add builds two executors: ours for the details read (the host clock), then the
    # shared host's ``direct_add`` (its own context, see the vendor pin).
    ours = seen[0::2]
    assert [context.timezone for context in ours] == ["America/Chicago", "Europe/Berlin"]
    for context in ours:
        assert context.now is not None and context.now.utcoffset() is not None
        assert context.now.tzinfo == ZoneInfo(context.timezone)


def test_storefront_focus_reads_details_so_the_pdp_enters_provenance(client, monkeypatch):
    _bind_replay(monkeypatch)
    headers = start(client)
    response = client.post(
        "/api/session/focus", json={"product_id": PRODUCT_ID}, headers=headers
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert body["product_id"] == PRODUCT_ID
    assert "T-Shirt" in body["title"]
    record = main_module.host.sessions.require(headers[SESSION_HEADER])
    assert PRODUCT_ID in record.state.seen_products
    assert VARIANT_S in record.state.seen_products
    assert any("storefront" in event.lower() for event in record.pending_app_events)


def test_sync_catalog_puts_grid_titles_into_the_session(client, monkeypatch):
    _bind_replay(monkeypatch)
    headers = start(client)
    response = client.post("/api/session/sync-catalog", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["products"] >= 3
    record = main_module.host.sessions.require(headers[SESSION_HEADER])
    assert MAIN_ID in record.state.seen_products
    assert PRODUCT_ID in record.state.seen_products
    assert any("Main product" in event for event in record.pending_app_events)


def test_the_add_button_on_a_family_is_held_with_the_route_to_a_variant(client, monkeypatch):
    _bind_replay(monkeypatch)
    response = client.post(
        "/api/cart/add", json={"product_id": PRODUCT_ID, "quantity": 1}, headers=start(client)
    )
    assert response.status_code == 400
    assert (
        "variant" in response.json()["detail"].lower()
        or "option" in response.json()["detail"].lower()
    )


def test_the_add_button_on_an_unknown_product_is_404(client, monkeypatch):
    _bind_replay(monkeypatch)
    response = client.post(
        "/api/cart/add",
        json={"product_id": "ffffffffffffffffffffffffffffffff", "quantity": 1},
        headers=start(client),
    )
    assert response.status_code == 404


def test_the_handoff_page_mints_a_one_time_code_and_posts_it_to_the_shop(client, monkeypatch):
    _bind_replay(monkeypatch)
    headers = start(client)
    added = client.post(
        "/api/cart/add", json={"product_id": VARIANT_S, "quantity": 1}, headers=headers
    ).json()
    ticket_url = added["checkout_url"]
    path = ticket_url[len("http://host.test") :]
    page = client.get(path)
    assert page.status_code == 200
    assert page.headers["cache-control"] == "no-store"
    html = page.text
    assert 'method="post" action="http://shopware.test/claude-commerce/continue"' in html
    assert CART_ID not in html
    code = re.search(r'name="code" value="([^"]+)"', html).group(1)
    assert HandoffCodeVerifier(HANDOFF_SECRET).verify(code) == CART_ID
    # A second click mints a fresh code (the plugin refuses replays of the first).
    second = re.search(r'name="code" value="([^"]+)"', client.get(path).text).group(1)
    assert second != code
    assert client.get("/api/checkout/handoff/unknown-ticket").status_code == 404


def test_the_handoff_page_refuses_when_the_cart_is_gone(client, monkeypatch):
    _bind_replay(monkeypatch)
    headers = start(client)
    added = client.post(
        "/api/cart/add", json={"product_id": VARIANT_S, "quantity": 1}, headers=headers
    ).json()
    path = added["checkout_url"][len("http://host.test") :]
    client.post("/api/reset", json={}, headers=headers)
    assert client.get(path).status_code == 404


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


# ---------------------------------------------------------------------------- identity linking


def test_a_fresh_session_is_signed_out_and_says_why_linking_is_off(client):
    status = client.get("/api/auth/status", headers=start(client)).json()
    assert status["signed_in"] is False
    assert status["available"] is False
    assert "HTTPS" in status["reason"] or "signing key" in status["reason"]


def test_signin_start_requires_a_session(client):
    assert client.get("/api/auth/shopware/start", follow_redirects=False).status_code == 401


def test_signin_start_without_a_signer_or_https_profile_answers_503(client):
    response = client.get(
        "/api/auth/shopware/start", params={"session_id": start(client)[SESSION_HEADER]}
    )
    assert response.status_code == 503
    assert "Identity Linking" in response.json()["detail"]


def test_identity_linking_runs_the_signed_pkce_flow_and_adopts_the_customer_cart(
    client, monkeypatch
):
    signer = RequestSigner.generate()
    shop = _bind_replay(monkeypatch, signer=signer)
    linking = ShopwareIdentityLinking(
        main_module.backend.client,
        main_module.backend.store_api,
        public_url="http://localhost:8004",
        http=httpx.AsyncClient(transport=httpx.MockTransport(shop.handle)),
    )
    linking.client_id = "https://platform.example/agent-profile.json"
    monkeypatch.setattr(main_module, "identity", linking)
    monkeypatch.setattr(main_module.backend, "_token_provider", linking.bearer)

    def customer_token(session_id: str) -> str | None:
        linked = linking.identity(session_id)
        return linked.customer_context_token if linked else None

    monkeypatch.setattr(main_module.backend, "_customer_token_provider", customer_token)
    headers = start(client)
    assert client.get("/api/auth/shopware/start", headers=headers).json()["mode"] == "credentials"

    bad = client.post(
        "/api/auth/shopware/login",
        json={"email": CUSTOMER_EMAIL, "password": "wrong"},
        headers=headers,
    )
    assert bad.status_code == 401

    ok = client.post(
        "/api/auth/shopware/login",
        json={"email": CUSTOMER_EMAIL, "password": CUSTOMER_PASSWORD},
        headers=headers,
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["signed_in"] is True
    assert client.get("/api/auth/status", headers=headers).json()["signed_in"] is True
    # The customer's context token is now the session's cart …
    assert client.get("/api/cart", headers=headers).json()["cart_id"] == CUSTOMER_TOKEN
    # … and UCP calls carry the linked bearer token.
    authorized = [
        r for r in shop.requests if r.url.path == "/ucp/mcp" and r.headers.get("authorization")
    ]
    assert authorized and authorized[-1].headers["authorization"] == "Bearer replay-access-token"
    authorize = next(r for r in shop.requests if r.url.path == "/ucp/v1/oauth/authorize")
    assert authorize.headers["sw-context-token"] == CUSTOMER_TOKEN
    assert authorize.headers["signature-input"].startswith("sig=(")
    assert "code_challenge_method=S256" in str(authorize.url)

    assert client.post("/api/auth/signout", headers=headers).json() == {"signed_in": False}
    assert client.get("/api/auth/status", headers=headers).json()["signed_in"] is False
