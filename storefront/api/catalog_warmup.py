# Copyright 2026 Shopware × Claude Commerce Agents authors.
# SPDX-License-Identifier: Apache-2.0

"""Fill the product grid display cache at startup. Uses UCP search, then Store API."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from shopping_agent import ShoppingSessionContext

if TYPE_CHECKING:
    from .shopware_backend import ShopwareStorefrontBackend

logger = logging.getLogger(__name__)


def warmup_enabled() -> bool:
    return os.environ.get("CATALOG_WARMUP", "1") != "0"


async def warm_catalog(backend: ShopwareStorefrontBackend) -> int:
    if not warmup_enabled():
        return 0
    session = ShoppingSessionContext(session_id="warmup", user_id="warmup")
    try:
        products = await backend.search_products(session, "", limit=24)
        if not products:
            products = await backend.search_products(session, "*", limit=24)
        if not products:
            products = await backend.search_products(session, "a", limit=24)
        for product in products:
            details = backend.products.get(product.product_id)
            if details:
                backend.warm_display_cache(details)
        # Warm-up must not leave provenance on a real session.
        backend.reset_session(session.session_id)
        logger.info("catalog warm-up cached %d products", len(products))
        return len(products)
    except Exception as failure:
        logger.warning("catalog warm-up skipped (%s); the grid fills from sessions", failure)
        return 0
