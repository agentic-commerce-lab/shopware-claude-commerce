# Copyright 2026 shopware AG
# SPDX-License-Identifier: MIT

"""Shopware storefront API: the shopping agent over a live Shopware UCP surface.

    uvicorn storefront.api.main:app --port 8004

Routes beyond the shared storefront host (``demo_common.build_storefront_host``):

    POST /api/cart/add                    the grid's add button (details → add, same gates)
    POST /api/cart/attach                 bind the session to an existing Shopware cart id
    GET  /api/checkout/handoff/{ticket}   mint a one-time handoff code and POST it to the shop
    GET  /api/auth/shopware/start         identity-linking availability + how to sign in
    POST /api/auth/shopware/login         link a Shopware customer (UCP OAuth + PKCE)
    GET  /api/auth/status  POST /api/auth/signout
    GET  /api/brand                       sales-channel branding for the web shell
    GET  /agent-profile.json              the UCP platform profile the shop fetches
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
from fastapi.responses import FileResponse, HTMLResponse
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
from shopware_common.anthropic_client import build_anthropic_client

from .agent_config import build_shopping_config
from .brand import BrandSource
from .catalog_warmup import warm_catalog
from .handoff import HandoffBroker, public_url_from_env
from .identity import SCOPES, IdentityError, IdentityUnavailable, ShopwareIdentityLinking
from .shopware_backend import ShopwareStorefrontBackend
from .store_api import StoreApiClient
from .ucp_client import UcpClient, shop_url_from_env

logger = logging.getLogger(__name__)

EXAMPLE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = EXAMPLE_ROOT / "data"
PROFILE_PATH = REPO_ROOT / "agent-profile.json"
STORE_NAME = "Shopware"

load_demo_env(EXAMPLE_ROOT)
_generated = REPO_ROOT / "docker" / ".generated.env"
if _generated.exists():
    for _key, _value in dotenv_values(_generated).items():
        if _value and not os.environ.get(_key):
            os.environ[_key] = _value

shop_url = shop_url_from_env()
public_url = public_url_from_env()
ucp_client = UcpClient(shop_url)
store_api = StoreApiClient(shop_url)
brand_source = BrandSource(store_api, fallback_name=STORE_NAME)
identity = ShopwareIdentityLinking(ucp_client, store_api, public_url=public_url)
handoff = HandoffBroker(shop_url, public_url=public_url)
backend = ShopwareStorefrontBackend(
    ucp_client,
    store_api=store_api,
    store_name=STORE_NAME,
    handoff=handoff,
    token_provider=identity.bearer,
    customer_token_provider=lambda sid: (
        linked.customer_context_token if (linked := identity.identity(sid)) else None
    ),
    on_auth_failure=identity.drop,
)
shopping_config = build_shopping_config(backend.store_name)
agent = ShoppingAgent(
    backend=backend,
    skills_dir=REPO_ROOT / "vendor" / "skills" / "shopping",
    config=shopping_config,
    memory_store=InMemoryMemoryStore(),
    client=build_anthropic_client(timeout=shopping_config.request_timeout_s),
)


def cart_extras(record) -> dict:
    """Folded into every cart payload: the handoff ticket URL and the Shopware cart id."""
    return {
        "checkout_url": backend.checkout_url_for(record.session_id),
        "cart_id": backend.cart_id_for(record.session_id),
    }


class CartAttachRequest(BaseModel):
    cart_id: str = Field(min_length=1, max_length=512)


class ShopwareLoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


host = build_storefront_host(
    title="Shopware storefront API",
    example_root=EXAMPLE_ROOT,
    backend=backend,
    agent=agent,
    memory_seeder=MemorySeeder(DATA_DIR / "memory-seed.json"),
    product_of=backend.products.get,
    cart_extras=cart_extras,
)
app = host.app

_host_lifespan = app.router.lifespan_context
_warmup_task: asyncio.Task | None = None


@asynccontextmanager
async def _lifespan_with_warmup(app_) -> AsyncIterator[None]:
    global _warmup_task
    async with _host_lifespan(app_):
        logger.info(
            "UCP transport %s (fallback %s), signing %s, handoff %s, identity linking %s",
            ucp_client.transport,
            "on" if ucp_client.fallback else "off",
            "on" if ucp_client.signs_requests else "off",
            "on" if handoff.configured else "off",
            "on" if identity.configured else f"off ({identity.unavailable_reason})",
        )
        _warmup_task = asyncio.create_task(warm_catalog(backend))
        try:
            await backend.policies.rebuild()
        except Exception:
            logger.warning("policy index rebuild failed; fallback copy is used", exc_info=True)
        try:
            yield
        finally:
            await ucp_client.aclose()


app.router.lifespan_context = _lifespan_with_warmup


@app.get("/agent-profile.json")
async def agent_profile() -> FileResponse:
    if not PROFILE_PATH.exists():
        raise HTTPException(status_code=404, detail="agent-profile.json missing")
    return FileResponse(PROFILE_PATH, media_type="application/json")


@app.post("/api/cart/add")
async def cart_add(request: CartAddRequest, record: host.CurrentSession) -> dict:
    """The grid button. It reads the product through the agent's own
    ``get_product_details`` tool first, so the record (and its variants) enter session
    provenance exactly as a conversation would, then adds through the same gated executor."""
    executor = agent.executor_class(
        backend=backend,
        config=agent.config,
        skills=agent.skills,
        session=host.context(record),
        state=record.state,
        memory=agent.memory,
    )
    details = await executor.execute("get_product_details", {"product_id": request.product_id})
    if details.is_error:
        raise HTTPException(status_code=404, detail="Product not found")
    host.sessions.save(record)
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


@app.get("/api/checkout/handoff/{ticket}", response_class=HTMLResponse)
async def checkout_handoff(ticket: str) -> HTMLResponse:
    """Click-time handoff: resolve the session behind the ticket, mint a one-time code
    for its cart and auto-submit it to the shop's ``/claude-commerce/continue``."""
    if not handoff.configured:
        raise HTTPException(
            status_code=503, detail="Checkout handoff is not configured on this host"
        )
    session_id = handoff.session_for(ticket)
    if session_id is None:
        raise HTTPException(status_code=404, detail="Unknown or expired checkout link")
    code = backend.handoff_code_for(session_id)
    if code is None:
        raise HTTPException(status_code=409, detail="This session has no cart to continue with")
    return HTMLResponse(handoff.page(code), headers={"Cache-Control": "no-store"})


@app.get("/api/auth/shopware/start")
async def shopware_signin_start(request: Request, session_id: str | None = None) -> dict:
    sid = session_id or request.headers.get(SESSION_HEADER)
    if not sid or host.sessions.read_state(sid) is None:
        raise HTTPException(status_code=401, detail="Start a session first (POST /api/session)")
    if not identity.configured:
        raise HTTPException(status_code=503, detail=identity.unavailable_reason)
    return {
        "mode": "credentials",
        "login": "/api/auth/shopware/login",
        "client_id": identity.client_id,
        "scopes": list(SCOPES),
    }


@app.post("/api/auth/shopware/login")
async def shopware_login(request: ShopwareLoginRequest, record: host.CurrentSession) -> dict:
    try:
        linked = await identity.link(record.session_id, request.email, request.password)
    except IdentityUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from None
    except IdentityError as error:
        raise HTTPException(status_code=401, detail=str(error)) from None
    # The customer's context token is also their cart: continue in it.
    await backend.attach_cart(record.session_id, linked.customer_context_token)
    return {"signed_in": True, "scope": linked.scope}


@app.get("/api/auth/status")
async def auth_status(record: host.CurrentSession) -> dict:
    return {
        "signed_in": identity.signed_in(record.session_id),
        "available": identity.configured,
        "reason": identity.unavailable_reason,
    }


@app.post("/api/auth/signout")
async def auth_signout(record: host.CurrentSession) -> dict:
    identity.drop(record.session_id)
    return {"signed_in": False}


@app.get("/api/brand")
async def brand(request: Request) -> dict:
    return await brand_source.brand(request.client.host if request.client else None)
