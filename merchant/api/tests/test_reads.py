# Copyright 2026 Shopware × Claude Commerce Agents authors.
# SPDX-License-Identifier: Apache-2.0

from merchant.api.fake_admin import OIL, SHIRT_S


async def test_search_and_listing_details(warmed, session):
    hits = await warmed.search_listings(session, "oil", None, 8)
    assert hits and hits[0].listing_id == OIL
    details = await warmed.get_listing(session, OIL)
    assert details is not None
    assert details.price == 12.9
    shirt = await warmed.get_listing(session, "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1")
    assert shirt is not None
    assert shirt.variants


async def test_snapshot_and_low_stock_alert(warmed, session):
    snapshot = await warmed.get_business_snapshot(session)
    assert snapshot.orders >= 1
    assert snapshot.currency == "EUR"
    alerts = await warmed.get_inventory_alerts(session)
    assert any(a.listing_id == SHIRT_S for a in alerts)


async def test_metrics_series(warmed, session):
    series = await warmed.query_metrics(session, "sales")
    assert series.points
    unknown = await warmed.query_metrics(session, "traffic")
    assert unknown.points == []
    assert unknown.note
