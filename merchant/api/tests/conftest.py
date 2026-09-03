# Copyright 2026 Shopware × Claude Commerce Agents authors.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pytest

from merchant_agent import MerchantSessionContext
from merchant.api.agent_config import ShopwareSettings, build_merchant_config
from merchant.api.fake_admin import OIL, SHIRT, SHIRT_S, FakeAdmin
from merchant.api.shopware_backend import ShopwareMerchantBackend


@pytest.fixture
def admin() -> FakeAdmin:
    return FakeAdmin()


@pytest.fixture
def settings() -> ShopwareSettings:
    return ShopwareSettings(
        shop_url="http://shopware.test",
        operator="Dana",
        store_name="Demo Shop",
        low_stock_default=8,
        local_store=True,
    )


@pytest.fixture
def backend(admin: FakeAdmin, settings: ShopwareSettings) -> ShopwareMerchantBackend:
    return ShopwareMerchantBackend(admin, settings, build_merchant_config("Demo Shop"))


@pytest.fixture
def session() -> MerchantSessionContext:
    return MerchantSessionContext(
        session_id="ms-1",
        merchant_id="http://shopware.test",
        operator="Dana",
    )


@pytest.fixture
async def warmed(backend: ShopwareMerchantBackend) -> ShopwareMerchantBackend:
    await backend.warm()
    return backend
