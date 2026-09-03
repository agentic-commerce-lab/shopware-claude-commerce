# Copyright 2026 Shopware × Claude Commerce Agents authors.
# SPDX-License-Identifier: Apache-2.0

"""Read the live Shopware Admin API. No Anthropic key. Default is --read-only.

    python merchant/scripts/smoke_live.py --read-only
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from dotenv import dotenv_values  # noqa: E402

from demo_common import load_demo_env  # noqa: E402
from merchant.api.admin_client import AdminClient  # noqa: E402
from merchant.api.agent_config import MissingCredentials, load_settings  # noqa: E402
from merchant.api.shopware_backend import ShopwareMerchantBackend  # noqa: E402
from merchant.api.agent_config import build_merchant_config  # noqa: E402
from merchant_agent import MerchantSessionContext  # noqa: E402

load_demo_env(REPO_ROOT / "merchant")
load_demo_env(REPO_ROOT)
generated = REPO_ROOT / "docker" / ".generated.env"
if generated.exists():
    for key, value in dotenv_values(generated).items():
        if value and not os.environ.get(key):
            os.environ[key] = value


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--read-only", action="store_true", default=True)
    parser.add_argument("--write", action="store_true", help="Opt in to a reversible price write")
    args = parser.parse_args()
    try:
        settings = load_settings()
    except MissingCredentials as error:
        print(error, file=sys.stderr)
        sys.exit(1)
    if settings.local_store:
        print("SHOPWARE_LOCAL_STORE=1 — smoke_live needs a real Admin API.", file=sys.stderr)
        sys.exit(1)
    admin = AdminClient(
        settings.shop_url,
        username=settings.username,
        password=settings.password,
        access_key=settings.access_key,
        secret_key=settings.secret_key,
    )
    backend = ShopwareMerchantBackend(admin, settings, build_merchant_config(settings.store_name or "Shopware"))
    session = MerchantSessionContext(
        session_id="smoke", merchant_id=settings.merchant_id, operator=settings.operator
    )
    await backend.warm()
    listings = backend.all_listings()
    print(f"catalog: {len(listings)} listings")
    snapshot = await backend.get_business_snapshot(session)
    print(f"snapshot: sales={snapshot.sales} orders={snapshot.orders} {snapshot.currency}")
    alerts = await backend.get_inventory_alerts(session)
    print(f"alerts: {len(alerts)} low-stock/slow-mover")
    if args.write:
        print("write path is reserved; this smoke stays read-only unless you extend it.")
    await admin.aclose()
    print(f"smoke_live ok against {settings.shop_url}")


if __name__ == "__main__":
    asyncio.run(main())
