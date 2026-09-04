# Copyright 2026 shopware AG
# SPDX-License-Identifier: MIT

"""Shopware storefront API: the shopping agent over a live Shopware UCP surface.

    uvicorn storefront.api.main:app --port 8004

Routes beyond the shared storefront host (``demo_common.build_storefront_host``):

    POST /api/cart/add                    the grid's add button (details → add, same gates)
    POST /api/session/focus               storefront PDP → get_product_details + app-event (H7)
    POST /api/session/sync-catalog        grid catalog → session provenance
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
from shopping_agent import ShoppingSessionContext
from shopping_agent_runtime import ShoppingAgent
from shopware_common.anthropic_client import build_anthropic_client
from shopware_common.clock import host_clock

from .agent_config import build_shopping_config
from .agent_tools import ShoppingAgentTools
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
# SwagCommerceAgentTools on /store-api/_mcp (SHOPWARE_AGENT_TOOLS=plugin|host, auto-detected).
agent_tools = ShoppingAgentTools(shop_url, store_api.access_key)
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
    agent_tools=agent_tools,
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


class ProductFocusRequest(BaseModel):
    product_id: str = Field(min_length=1, max_length=64)


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
        await agent_tools.detect()
        logger.info(
            "UCP transport %s (fallback %s), signing %s, handoff %s, identity linking %s, "
            "agent tools %s",
            ucp_client.transport,
            "on" if ucp_client.fallback else "off",
            "on" if ucp_client.signs_requests else "off",
            "on" if handoff.configured else "off",
            "on" if identity.configured else f"off ({identity.unavailable_reason})",
            agent_tools.description,
        )
        _warmup_task = asyncio.create_task(warm_catalog(backend, shopping_config))
        # The host index stays warm as the fallback of the plugin path.
        try:
            await backend.policies.rebuild()
        except Exception:
            logger.warning("policy index rebuild failed; fallback copy is used", exc_info=True)
        try:
            yield
        finally:
            await agent_tools.aclose()
            await ucp_client.aclose()


app.router.lifespan_context = _lifespan_with_warmup


@app.get("/agent-profile.json")
async def agent_profile() -> FileResponse:
    if not PROFILE_PATH.exists():
        raise HTTPException(status_code=404, detail="agent-profile.json missing")
    return FileResponse(PROFILE_PATH, media_type="application/json")


def shopping_context(record, request: Request | None = None) -> ShoppingSessionContext:
    """This host's view of a request: identity from the record, the clock from the
    browser's zone (``X-Timezone`` / ``tz``) or ``HOST_TIMEZONE``, as an aware ``now``.
    (The shared host's ``/api/chat`` builds its own context inside ``demo_common``.)"""
    return ShoppingSessionContext(
        session_id=record.session_id, user_id=record.user_id, **host_clock(request)
    )


def _shopping_executor(record, http_request: Request | None = None):
    return agent.executor_class(
        backend=backend,
        config=agent.config,
        skills=agent.skills,
        session=shopping_context(record, http_request),
        state=record.state,
        memory=agent.memory,
    )


async def ingest_grid_catalog(record, http_request: Request | None = None) -> int:
    """Put the products the grid already shows into session provenance (H7).

    The grid reads ``backend.products``; chat only sees ``seen_products`` after a tool
    call. One listing search (same catalog as ``GET /api/products``) closes that gap.
    """
    if record.state.seen_products:
        return len(record.state.seen_products)
    executor = _shopping_executor(record, http_request)
    await executor.execute("search_products", {"query": "", "limit": 24})
    if not record.state.seen_products:
        for product_id in list(backend.products)[:24]:
            await executor.execute("get_product_details", {"product_id": product_id})
    titles: list[str] = []
    seen: set[str] = set()
    for details in backend.products.values():
        title = (details.title or "").strip()
        if title and title not in seen:
            seen.add(title)
            titles.append(title)
    if titles:
        note = (
            "The storefront product grid is showing: "
            + ", ".join(titles[:12])
            + ". Those are this shop's live products — look them up with "
            "search_products or get_product_details (the exact title is enough) "
            "instead of inventing aisles or saying they are not in view."
        )
        if note not in record.pending_app_events:
            record.pending_app_events.append(note)
    host.sessions.save(record)
    return len(record.state.seen_products)


@app.middleware("http")
async def sync_catalog_before_chat(request: Request, call_next):
    if request.method == "POST" and request.url.path.rstrip("/").endswith("/api/chat"):
        session_id = request.headers.get(SESSION_HEADER)
        if session_id:
            try:
                record = host.sessions.require(session_id)
                await ingest_grid_catalog(record, request)
            except Exception:
                logger.exception("catalog sync before chat failed")
    return await call_next(request)


@app.post("/api/cart/add")
async def cart_add(
    request: CartAddRequest, http_request: Request, record: host.CurrentSession
) -> dict:
    """The grid button. It reads the product through the agent's own
    ``get_product_details`` tool first, so the record (and its variants) enter session
    provenance exactly as a conversation would, then adds through the same gated executor."""
    executor = _shopping_executor(record, http_request)
    details = await executor.execute("get_product_details", {"product_id": request.product_id})
    if details.is_error:
        raise HTTPException(status_code=404, detail="Product not found")
    host.sessions.save(record)
    return await host.direct_add(
        record,
        request,
        note="Customer tapped the add-to-cart button on {title} ({product_id}), quantity {quantity}.",
    )


@app.post("/api/session/focus")
async def session_focus(
    request: ProductFocusRequest, http_request: Request, record: host.CurrentSession
) -> dict:
    """Storefront navigation: the visitor opened a PDP. Read it through
    ``get_product_details`` so the record (and its variants) enter provenance (H7),
    then queue an app-event note the next chat turn hands to the model."""
    executor = _shopping_executor(record, http_request)
    details = await executor.execute("get_product_details", {"product_id": request.product_id})
    if details.is_error:
        raise HTTPException(status_code=404, detail="Product not found")
    product = record.state.seen_products.get(request.product_id) or backend.products.get(
        request.product_id
    )
    title = product.title if product is not None else request.product_id
    note = (
        f"The customer opened {title} on the Shopware storefront "
        f"(product_id {request.product_id}). Treat it as the current product "
        "until they navigate away or search for something else."
    )
    if note not in record.pending_app_events:
        record.pending_app_events.append(note)
    host.sessions.save(record)
    return {"ok": True, "product_id": request.product_id, "title": title}


@app.post("/api/session/sync-catalog")
async def session_sync_catalog(http_request: Request, record: host.CurrentSession) -> dict:
    """Customer-demo grid → session: the products ``GET /api/products`` already shows."""
    count = await ingest_grid_catalog(record, http_request)
    return {"ok": True, "products": count}


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
