# Copyright 2026 Shopware × Claude Commerce Agents authors.
# SPDX-License-Identifier: Apache-2.0

"""Live check of the storefront backend against Docker Shopware. No Anthropic key.

    python storefront/scripts/smoke.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from dotenv import dotenv_values  # noqa: E402

from demo_common import load_demo_env  # noqa: E402
from shopping_agent import ShoppingSessionContext  # noqa: E402
from storefront.api.shopware_backend import ShopwareStorefrontBackend  # noqa: E402
from storefront.api.store_api import StoreApiClient  # noqa: E402
from storefront.api.ucp_client import UcpClient, shop_url_from_env  # noqa: E402

load_demo_env(REPO_ROOT)
generated = REPO_ROOT / "docker" / ".generated.env"
if generated.exists():
    import os

    for key, value in dotenv_values(generated).items():
        if value and not os.environ.get(key):
            os.environ[key] = value


async def main() -> None:
    shop = shop_url_from_env()
    client = UcpClient(shop)
    store_api = StoreApiClient(shop)
    backend = ShopwareStorefrontBackend(client, store_api=store_api, store_name="Shopware")
    session = ShoppingSessionContext(session_id="smoke", user_id="guest")

    try:
        discovery = await client.discover()
    except Exception as error:
        print(f"discovery FAILED against {shop}: {error}", file=sys.stderr)
        sys.exit(1)
    version = (discovery.get("ucp") or {}).get("version", "?")
    print(f"discovery: ucp version {version}")

    products = await backend.search_products(session, "shirt", limit=3)
    if not products:
        products = await backend.search_products(session, "*", limit=3)
    assert products, "search returned nothing"
    first = products[0]
    print(f"search: {len(products)} products, first {first.title!r} {first.price} {first.currency}")

    details = await backend.get_product_details(session, first.product_id)
    assert details is not None, "details missing"
    print(f"details: title={details.title!r} variants={len(details.variants)}")
    if "Claude Commerce T-Shirt" in (details.title or ""):
        assert len(details.variants) >= 2, "seeded T-shirt should list size variants"

    sku = first.product_id
    if details.variants:
        in_stock = next((v for v in details.variants if v.in_stock), details.variants[0])
        sku = in_stock.product_id

    cart = await backend.add_to_cart(session, sku, 1)
    assert cart.item_count >= 1, f"expected items, got {cart.item_count}"
    checkout_url = await backend.checkout_url_for(session.session_id)
    assert checkout_url, "cart carried no continue_url / checkout handoff"
    print(f"cart: added {cart.items[0].title!r}, checkout_url={checkout_url}")

    cart = await backend.update_cart_item(session, cart.items[0].product_id, 2)
    assert cart.item_count >= 2, f"expected quantity 2, got {cart.item_count}"
    cart = await backend.remove_from_cart(session, cart.items[0].product_id)
    print("cart: update and remove ok")

    policies = await backend.search_policies(session, "widerruf")
    print(f"policies: {len(policies)} matches")

    await client.aclose()
    await store_api.aclose()
    print(f"smoke ok against {shop}")


if __name__ == "__main__":
    asyncio.run(main())
