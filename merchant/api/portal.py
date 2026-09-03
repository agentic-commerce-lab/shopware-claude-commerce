# Copyright 2026 shopware AG
# SPDX-License-Identifier: MIT

"""The merchant web UI's own reads, next to the blueprint router:

    GET /api/merchant/dashboard?period=last_7d   KPIs with sparklines and a digest line
    GET /api/merchant/orders?limit=20            recent Shopware orders with issue tags
    GET /api/merchant/changes?status=staged      the ledger (staged|applied|discarded|all)

They are scoped exactly like the blueprint's portal reads: the caller must present the
``X-Session-Id`` of a session started on ``POST /api/merchant/session``. The blueprint
router keeps its session store private, so this module borrows the very dependency its
own routes declare (``_session_dependency_of``) instead of building a second store.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.routing import APIRoute

from demo_common.sessions import SessionRecord
from merchant_agent import ChangeStatus, MerchantSessionContext

from .shopware_backend import ShopwareMerchantBackend

CHANGE_STATUSES = ("staged", "applied", "discarded", "all")
ORDERS_DEFAULT_LIMIT = 20
ORDERS_MAX_LIMIT = 100
_PROBE_PATH = "/alerts"


def _session_dependency_of(router: APIRouter) -> Callable[..., Any]:
    """The ``current_session`` callable the blueprint router's scoped routes depend on."""
    for route in router.routes:
        if isinstance(route, APIRoute) and route.path == _PROBE_PATH:
            for dependant in route.dependant.dependencies:
                if dependant.call is not None:
                    return dependant.call
    raise RuntimeError("the merchant router exposes no session-scoped route to borrow")


def build_portal_router(
    backend: ShopwareMerchantBackend, merchant_router: APIRouter, *, operator: str
) -> APIRouter:
    current_session = _session_dependency_of(merchant_router)
    # A default-value ``Depends`` rather than an ``Annotated`` alias: the alias is local to
    # this function and postponed annotations could not resolve it.
    scoped = Depends(current_session, scope="function")
    router = APIRouter()

    def context(record: SessionRecord) -> MerchantSessionContext:
        return MerchantSessionContext(
            session_id=record.session_id,
            merchant_id=record.user_id,
            operator=operator,
            now=datetime.now(),
        )

    @router.get("/dashboard")
    async def dashboard(
        period: str = Query(default="last_7d"), record: SessionRecord = scoped
    ) -> dict[str, Any]:
        return await backend.dashboard(context(record), period)

    @router.get("/orders")
    async def orders(
        limit: int = Query(default=ORDERS_DEFAULT_LIMIT, ge=1, le=ORDERS_MAX_LIMIT),
        record: SessionRecord = scoped,
    ) -> dict[str, Any]:
        del record
        return {"orders": await backend.portal_orders(limit)}

    @router.get("/changes")
    async def changes(
        status: str = Query(default="staged"), record: SessionRecord = scoped
    ) -> dict[str, Any]:
        wanted = status.strip().lower()
        if wanted not in CHANGE_STATUSES:
            wanted = "staged"
        listed = backend.changes(wanted)
        # The portal's Approve / Dismiss buttons go through the blueprint's provenance gate,
        # which accepts only change ids this session has seen. Listing a staged change to
        # the operator is that sighting (exactly what the ``get_pending_changes`` tool does),
        # so a change staged in an earlier session or before a restart stays actionable.
        for change in listed:
            if change.status == ChangeStatus.STAGED:
                record.state.remember_change(change)
        return {
            "status": wanted,
            "changes": [change.model_dump(mode="json", exclude_none=True) for change in listed],
        }

    return router
