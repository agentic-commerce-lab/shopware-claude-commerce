# Copyright 2026 Shopware × Claude Commerce Agents authors.
# SPDX-License-Identifier: Apache-2.0

"""Portal wiring: shared merchant router over Shopware Admin REST."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter

from commerce_common.memory import MemoryStore
from demo_common import MerchantIdentity, build_merchant_router
from merchant_agent_runtime import MerchantAgent

from .admin_client import AdminClient
from .agent_config import DATA_DIR, SKILLS_DIR, ShopwareSettings, build_merchant_config
from .fake_admin import FakeAdmin
from .shopware_backend import ShopwareMerchantBackend
from .store_view import ShopwareStoreView


@dataclass(frozen=True)
class MerchantPortal:
    router: APIRouter
    backend: ShopwareMerchantBackend
    client: AdminClient | None


def create_merchant_portal(
    settings: ShopwareSettings,
    memory_store: MemoryStore,
    *,
    admin=None,
) -> MerchantPortal:
    live: AdminClient | None = None
    if admin is None:
        if settings.local_store:
            admin = FakeAdmin.from_seed(DATA_DIR / "seed.json")
        else:
            live = AdminClient(
                settings.shop_url,
                username=settings.username,
                password=settings.password,
                access_key=settings.access_key,
                secret_key=settings.secret_key,
            )
            admin = live
    config = build_merchant_config(settings.store_name or settings.shop_url)
    backend = ShopwareMerchantBackend(admin, settings, config)
    store_view = ShopwareStoreView(backend)
    agent = MerchantAgent(
        backend=backend,
        skills_dir=SKILLS_DIR,
        config=config,
        memory_store=memory_store,
    )
    router = build_merchant_router(
        storefront=store_view,
        backend=backend,
        agent=agent,
        identity=MerchantIdentity(merchant_id=settings.merchant_id, operator=settings.operator),
        example_dir="merchant",
    )
    return MerchantPortal(router=router, backend=backend, client=live)
