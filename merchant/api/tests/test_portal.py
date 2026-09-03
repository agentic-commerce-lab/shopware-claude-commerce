# Copyright 2026 shopware AG
# SPDX-License-Identifier: MIT

"""The portal's own routes over ``TestClient`` and ``FakeAdmin``: session scoping, the
dashboard/orders/changes payload shapes, and the overview extras."""

from __future__ import annotations

import asyncio
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from commerce_common.memory import JsonFileMemoryStore
from merchant.api.fake_admin import OIL, FakeAdmin
from merchant.api.merchant import create_merchant_portal
from merchant_agent import MerchantSessionContext, PriceUpdateItem

PREFIX = "/api/merchant"


@pytest.fixture
def client(monkeypatch, settings, now, tmp_path: Path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    admin = FakeAdmin(now=now)
    portal = create_merchant_portal(
        settings, JsonFileMemoryStore(tmp_path / "memory.json"), admin=admin, clock=lambda: now
    )
    app = FastAPI()
    app.include_router(portal.router, prefix=PREFIX)
    app.include_router(portal.portal_router, prefix=PREFIX)
    asyncio.run(portal.backend.warm())
    with TestClient(app) as test_client:
        test_client.merchant_portal = portal  # type: ignore[attr-defined]
        yield test_client
    portal.backend.ledger.close()


def _session(client: TestClient) -> dict[str, str]:
    response = client.post(f"{PREFIX}/session")
    assert response.status_code == 200, response.text
    return {"X-Session-Id": response.headers.get("X-Session-Id") or response.json()["session_id"]}


def test_routes_require_a_session(client: TestClient):
    for path in ("/dashboard", "/orders", "/changes"):
        assert client.get(f"{PREFIX}{path}").status_code == 401
    assert client.get(f"{PREFIX}/dashboard", headers={"X-Session-Id": "bogus"}).status_code == 401


def test_overview_carries_shop_extras_and_recent_orders(client: TestClient):
    headers = _session(client)
    overview = client.get(f"{PREFIX}/overview", headers=headers).json()
    assert overview["shop"] == {
        "name": "Storefront",
        "operator": "Dana",
        "currency": "EUR",
        "transport": "fake",
        "sales_channel": "eeeeeeeeeeeeeeeeeeeeeeeeeeeeee01",
    }
    assert overview["recent_orders"] and overview["recent_orders"][0]["order_id"] == "10001"
    assert overview["snapshot"]["orders"] > 0 and overview["needs_attention"]["order_issues"]


def test_dashboard_payload_shape(client: TestClient):
    headers = _session(client)
    body = client.get(f"{PREFIX}/dashboard", params={"period": "last_7d"}, headers=headers).json()
    assert body["period"] == {
        "label": "Aug 28 – Sep 3",
        "against": "the prior week",
        "key": "last_7d",
    }
    kpis = body["kpis"]
    assert set(kpis) == {"sales", "orders", "conversion", "average_order"}
    assert kpis["sales"]["unit"] == "EUR" and len(kpis["sales"]["points"]) == 7
    assert set(kpis["sales"]["points"][0]) == {"date", "value"}
    assert kpis["orders"]["unit"] == "count" and kpis["orders"]["value"] > 0
    assert kpis["conversion"]["value"] is None and "traffic" in kpis["conversion"]["note"]
    assert kpis["average_order"]["value"] == round(
        kpis["sales"]["value"] / kpis["orders"]["value"], 2
    )
    assert body["digest"].startswith("Sales are ") and body["digest"].endswith(" need you today.")
    assert "orders and" in body["digest"] and "listings" in body["digest"]
    monthly = client.get(
        f"{PREFIX}/dashboard", params={"period": "last_30d"}, headers=headers
    ).json()
    assert (
        monthly["period"]["against"] == "the prior 30 days"
        and len(monthly["kpis"]["sales"]["points"]) == 30
    )


def test_dashboard_context_carries_the_operators_clock(client: TestClient, monkeypatch):
    """The session context the route builds is aware and in the browser's zone
    (``X-Timezone``), and falls back to ``HOST_TIMEZONE`` when the header is absent."""
    headers = _session(client)
    backend = client.merchant_portal.backend  # type: ignore[attr-defined]
    seen: list[MerchantSessionContext] = []
    real_dashboard = backend.dashboard

    async def spy(context, period):
        seen.append(context)
        return await real_dashboard(context, period)

    monkeypatch.setattr(backend, "dashboard", spy)
    monkeypatch.setenv("HOST_TIMEZONE", "Europe/Berlin")

    client.get(f"{PREFIX}/dashboard", headers={**headers, "X-Timezone": "Asia/Tokyo"})
    client.get(f"{PREFIX}/dashboard", headers=headers)
    client.get(f"{PREFIX}/dashboard", headers={**headers, "X-Timezone": "Nowhere/Land"})

    zones = [context.timezone for context in seen]
    assert zones == ["Asia/Tokyo", "Europe/Berlin", "Europe/Berlin"]
    for context in seen:
        assert context.now is not None and context.now.utcoffset() is not None
        assert context.now.tzinfo == ZoneInfo(context.timezone)


def test_orders_payload_shape(client: TestClient):
    headers = _session(client)
    body = client.get(f"{PREFIX}/orders", params={"limit": 5}, headers=headers).json()
    assert len(body["orders"]) == 5
    first = body["orders"][0]
    assert set(first) >= {
        "order_id", "order_number", "status", "placed_at", "total", "currency", "items", "customer"
    }  # fmt: skip
    assert (
        first["order_number"] == "10001"
        and first["currency"] == "EUR"
        and first["customer"] == "Dana Buyer 1"
    )
    tagged = [o for o in body["orders"] if "issue" in o]
    assert tagged and tagged[0]["issue"] == "buyer_message"
    assert client.get(f"{PREFIX}/orders", params={"limit": 0}, headers=headers).status_code == 422


def test_changes_route_filters_by_status(client: TestClient):
    headers = _session(client)
    backend = client.merchant_portal.backend  # type: ignore[attr-defined]
    context = MerchantSessionContext(session_id="s", merchant_id="m", operator="Dana")
    staged = asyncio.run(
        backend.stage_price_update(context, [PriceUpdateItem(listing_id=OIL, new_price=13.5)])
    )
    applied = asyncio.run(
        backend.stage_price_update(context, [PriceUpdateItem(listing_id=OIL, new_price=13.0)])
    )
    asyncio.run(backend.apply_change(context, applied.change_id))
    body = client.get(f"{PREFIX}/changes", headers=headers).json()
    assert body["status"] == "staged" and [c["change_id"] for c in body["changes"]] == [
        staged.change_id
    ]
    assert body["changes"][0]["items"][0]["target"] == OIL
    applied_body = client.get(
        f"{PREFIX}/changes", params={"status": "applied"}, headers=headers
    ).json()
    assert [c["change_id"] for c in applied_body["changes"]] == [applied.change_id]
    everything = client.get(f"{PREFIX}/changes", params={"status": "all"}, headers=headers).json()
    assert len(everything["changes"]) == 2
    assert (
        client.get(f"{PREFIX}/changes", params={"status": "weird"}, headers=headers).json()[
            "status"
        ]
        == "staged"
    )


def test_listing_a_staged_change_makes_its_portal_buttons_actionable(client: TestClient):
    # A change staged in another session (or before a restart) is unknown to this session's
    # provenance until the portal lists it; without that sighting Approve is held by the gate.
    backend = client.merchant_portal.backend  # type: ignore[attr-defined]
    elsewhere = MerchantSessionContext(session_id="other", merchant_id="m", operator="Dana")
    staged = asyncio.run(
        backend.stage_price_update(elsewhere, [PriceUpdateItem(listing_id=OIL, new_price=13.5)])
    )
    headers = _session(client)
    unseen = client.post(f"{PREFIX}/changes/{staged.change_id}/discard", headers=headers).json()
    assert unseen["ok"] is False and "not staged or listed in this session" in unseen["reason"]

    listed = client.get(f"{PREFIX}/changes", headers=headers).json()
    assert [c["change_id"] for c in listed["changes"]] == [staged.change_id]
    dismissed = client.post(f"{PREFIX}/changes/{staged.change_id}/discard", headers=headers).json()
    assert dismissed["ok"] is True and dismissed["change"]["status"] == "discarded"
    assert dismissed["change"]["discarded_by_kind"] == "operator"
