# Copyright 2026 Shopware × Claude Commerce Agents authors.
# SPDX-License-Identifier: Apache-2.0

"""Shopware storefront API: shopping agent over a live Shopware UCP surface.

    uvicorn storefront.api.main:app --port 8004
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import dotenv_values
from fastapi import HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from commerce_common.memory import InMemoryMemoryStore
from demo_common import (
    REPO_ROOT,
    SESSION_HEADER,
    CartAddRequest,
    MemorySeeder,
    build_storefront_host,
    load_demo_env,
)
from shopping_agent_runtime import ShoppingAgent

from .agent_config import build_shopping_config
from .brand import BrandSource
from .catalog_warmup import warm_catalog
from .identity import ShopwareSignIn
from .shopware_backend import ShopwareStorefrontBackend
from .store_api import StoreApiClient
from .ucp_client import UcpClient, shop_url_from_env

logger = logging.getLogger(__name__)

EXAMPLE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = EXAMPLE_ROOT / "data"

load_demo_env(EXAMPLE_ROOT)
_generated = REPO_ROOT / "docker" / ".generated.env"
if _generated.exists():
    for _key, _value in dotenv_values(_generated).items():
        if _value and not os.environ.get(_key):
            os.environ[_key] = _value

shop_url = shop_url_from_env()
signin = ShopwareSignIn()
store_api = StoreApiClient(shop_url)
brand_source = BrandSource(store_api, fallback_name="Shopware")
backend = ShopwareStorefrontBackend(
    UcpClient(shop_url),
    store_api=store_api,
    store_name="Shopware",
)
agent = ShoppingAgent(
    backend=backend,
    skills_dir=REPO_ROOT / "vendor" / "skills" / "shopping",
    config=build_shopping_config(backend.store_name),
    memory_store=InMemoryMemoryStore(),
)


async def cart_extras(record) -> dict:
    return {
        "checkout_url": await backend.checkout_url_for(record.session_id),
        "cart_id": backend.cart_id_for(record.session_id),
    }


class CartAttachRequest(BaseModel):
    cart_id: str = Field(min_length=1, max_length=512)


host = build_storefront_host(
    title="Shopware storefront API",
    example_root=EXAMPLE_ROOT,
    backend=backend,
    agent=agent,
    memory_seeder=MemorySeeder(DATA_DIR / "memory-seed.json"),
    cart_extras=cart_extras,
)
app = host.app

_start_session = host.sessions.start


def _start_session_with_grid_provenance(user_id: str):
    """Products already on the grid (catalog warmup) count as seen for this session."""
    record = _start_session(user_id)
    seen = []
    for details in backend.products.values():
        seen.append(details)
        seen.extend(getattr(details, "variants", []) or [])
    if seen:
        record.state.remember_products(seen)
        host.sessions.save(record)
    return record


host.sessions.start = _start_session_with_grid_provenance

_host_lifespan = app.router.lifespan_context
_warmup_task: asyncio.Task | None = None


@asynccontextmanager
async def _lifespan_with_warmup(app_) -> AsyncIterator[None]:
    global _warmup_task
    async with _host_lifespan(app_):
        _warmup_task = asyncio.create_task(warm_catalog(backend))
        try:
            await backend.policies.rebuild()
        except Exception:
            logger.warning("policy index rebuild failed; fallback copy is used")
        yield


app.router.lifespan_context = _lifespan_with_warmup

PROFILE_PATH = REPO_ROOT / "agent-profile.json"


@app.get("/agent-profile.json")
async def agent_profile() -> FileResponse:
    if not PROFILE_PATH.exists():
        raise HTTPException(status_code=404, detail="agent-profile.json missing")
    return FileResponse(PROFILE_PATH, media_type="application/json")


@app.post("/api/cart/add")
async def cart_add(request: CartAddRequest, record: host.CurrentSession) -> dict:
    return await host.direct_add(
        record,
        request,
        note="Customer tapped the add-to-cart button on {title} ({product_id}), quantity {quantity}.",
    )


@app.post("/api/cart/attach")
async def cart_attach(request: CartAttachRequest, record: host.CurrentSession) -> dict:
    if await backend.attach_cart(record.session_id, request.cart_id) is None:
        raise HTTPException(status_code=404, detail="The shop doesn't know that cart")
    return await host.cart_payload(record)


@app.get("/api/auth/shopware/start")
async def shopware_signin_start(request: Request, session_id: str | None = None) -> dict:
    sid = session_id or request.headers.get(SESSION_HEADER)
    if not sid or host.sessions.read_state(sid) is None:
        raise HTTPException(status_code=401, detail="Start a session first (POST /api/session)")
    if not signin.configured:
        raise HTTPException(
            status_code=503,
            detail="Identity Linking needs SHOPWARE_UCP_OAUTH_CLIENT_ID and "
            "SHOPWARE_UCP_OAUTH_CLIENT_SECRET. Guest mode still works.",
        )
    raise HTTPException(status_code=503, detail="Identity Linking is not wired in this first version.")


@app.get("/api/auth/status")
async def auth_status(record: host.CurrentSession) -> dict:
    return {"signed_in": signin.signed_in(record.session_id)}


@app.post("/api/auth/signout")
async def auth_signout(record: host.CurrentSession) -> dict:
    signin.drop(record.session_id)
    return {"signed_in": False}


@app.get("/api/brand")
async def brand(request: Request) -> dict:
    return await brand_source.brand(request.client.host if request.client else None)
