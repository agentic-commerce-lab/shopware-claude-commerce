# Copyright 2026 shopware AG
# SPDX-License-Identifier: MIT

"""Portal wiring: the shared merchant router plus the portal's own reads, over the
Shopware Admin transport named by ``SHOPWARE_ADMIN_TRANSPORT`` (MCP by default)."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter

from commerce_common.memory import MemoryStore
from demo_common import MerchantIdentity, build_merchant_router
from merchant_agent_runtime import MerchantAgent
from shopware_common.anthropic_client import build_anthropic_client

from .admin_client import AdminTransport, build_transport
from .agent_config import DATA_DIR, SKILLS_DIR, ShopwareSettings, build_merchant_config
from .fake_admin import FakeAdmin
from .portal import build_portal_router
from .shopware_backend import Clock, ShopwareMerchantBackend
from .store_view import ShopwareStoreView


@dataclass(frozen=True)
class MerchantPortal:
    router: APIRouter
    portal_router: APIRouter
    backend: ShopwareMerchantBackend
    client: AdminTransport


def create_merchant_portal(
    settings: ShopwareSettings,
    memory_store: MemoryStore,
    *,
    admin: AdminTransport | None = None,
    clock: Clock | None = None,
) -> MerchantPortal:
    if admin is None:
        if settings.local_store:
            admin = FakeAdmin.from_seed(
                DATA_DIR / "seed.json", sales_channel_id=settings.sales_channel_id
            )
        else:
            admin = build_transport(
                settings.transport,
                settings.shop_url,
                access_key=settings.access_key,
                secret_key=settings.secret_key,
            )
    config = build_merchant_config(settings.store_name or settings.shop_url)
    backend = ShopwareMerchantBackend(admin, settings, config, clock=clock)
    store_view = ShopwareStoreView(backend)
    agent = MerchantAgent(
        backend=backend,
        skills_dir=SKILLS_DIR,
        config=config,
        memory_store=memory_store,
        client=build_anthropic_client(timeout=config.request_timeout_s),
    )
    router = build_merchant_router(
        storefront=store_view,
        backend=backend,
        agent=agent,
        identity=MerchantIdentity(merchant_id=settings.merchant_id, operator=settings.operator),
        example_dir="merchant",
        overview_extras=lambda: {"shop": backend.shop_info()},
    )
    portal_router = build_portal_router(backend, router, operator=settings.operator)
    return MerchantPortal(router=router, portal_router=portal_router, backend=backend, client=admin)
