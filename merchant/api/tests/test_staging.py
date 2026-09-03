# Copyright 2026 Shopware × Claude Commerce Agents authors.
# SPDX-License-Identifier: Apache-2.0

"""Staging never writes; apply is the only mutation."""

from __future__ import annotations

from merchant_agent import ChangeStatus, InventoryActionItem, PriceUpdateItem, PromotionDraft
from merchant_agent.changes import ChangeNotApplicable
from merchant.api.fake_admin import OIL, SHIRT, SHIRT_S, FakeAdmin
from merchant.api.shopware_backend import ShopwareMerchantBackend


async def test_no_staging_path_writes_to_the_store(warmed: ShopwareMerchantBackend, session, admin: FakeAdmin):
    await warmed.stage_listing_update(session, OIL, {"title": "Olive Oil 500 ml"})
    await warmed.stage_price_update(session, [PriceUpdateItem(listing_id=OIL, new_price=13.50)])
    await warmed.stage_inventory_action(
        session, [InventoryActionItem(listing_id=SHIRT_S, action="restock", quantity=5)]
    )
    await warmed.stage_promotion(
        session,
        PromotionDraft(
            name="Oil week",
            listing_ids=[OIL],
            discount_pct=10,
            starts="2026-09-01",
            ends="2026-09-07",
        ),
    )
    assert admin.calls == []
    assert len(await warmed.get_pending_changes(session)) == 4


async def test_stage_campaign_is_not_applicable(warmed: ShopwareMerchantBackend, session):
    from merchant_agent import CampaignDraft

    try:
        await warmed.stage_campaign(session, CampaignDraft(name="Email", budget=100.0))
        raise AssertionError("expected ChangeNotApplicable")
    except ChangeNotApplicable:
        pass


async def test_apply_writes_price_then_marks_applied(
    warmed: ShopwareMerchantBackend, session, admin: FakeAdmin
):
    change = await warmed.stage_price_update(
        session, [PriceUpdateItem(listing_id=OIL, new_price=13.50)]
    )
    assert change.status is ChangeStatus.STAGED
    applied = await warmed.apply_change(session, change.change_id)
    assert applied.status is ChangeStatus.APPLIED
    assert admin.calls
    method, path, payload = admin.calls[0]
    assert method == "PATCH"
    assert OIL in path
    assert payload["price"][0]["gross"] == 13.5


async def test_failed_write_leaves_change_staged(
    warmed: ShopwareMerchantBackend, session, admin: FakeAdmin
):
    change = await warmed.stage_price_update(
        session, [PriceUpdateItem(listing_id=OIL, new_price=13.50)]
    )

    async def boom(*_a, **_k):
        from merchant.api.admin_client import AdminAPIError

        raise AdminAPIError("refused")

    admin.patch = boom  # type: ignore[method-assign]
    try:
        await warmed.apply_change(session, change.change_id)
        raise AssertionError("expected ChangeNotApplicable")
    except ChangeNotApplicable as error:
        assert "still staged" in str(error)
    pending = await warmed.get_pending_changes(session)
    assert pending[0].change_id == change.change_id
