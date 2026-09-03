# Copyright 2026 Shopware × Claude Commerce Agents authors.
# SPDX-License-Identifier: Apache-2.0

"""Merchant settings and agent config. Credentials stay in this module."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from demo_common import host_approval_default
from merchant_agent import MerchantAgentConfig

EXAMPLE_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = EXAMPLE_ROOT / "data"
SKILLS_DIR = EXAMPLE_ROOT.parent / "vendor" / "skills" / "merchant"


class MissingCredentials(RuntimeError):
    pass


@dataclass(frozen=True)
class ShopwareSettings:
    shop_url: str
    username: str = field(repr=False, default="")
    password: str = field(repr=False, default="")
    access_key: str = field(repr=False, default="")
    secret_key: str = field(repr=False, default="")
    operator: str = "Operator"
    store_name: str | None = None
    low_stock_default: int = 8
    local_store: bool = False

    @property
    def merchant_id(self) -> str:
        return self.shop_url


def local_store_requested() -> bool:
    return (os.environ.get("SHOPWARE_LOCAL_STORE") or "0").strip() not in {"", "0", "false"}


def load_settings() -> ShopwareSettings:
    local = local_store_requested()
    shop_url = (os.environ.get("SHOPWARE_ADMIN_URL") or os.environ.get("SHOPWARE_URL") or "").strip()
    username = (os.environ.get("SHOPWARE_ADMIN_USERNAME") or "").strip()
    password = (os.environ.get("SHOPWARE_ADMIN_PASSWORD") or "").strip()
    access_key = (os.environ.get("SHOPWARE_INTEGRATION_ACCESS_KEY") or "").strip()
    secret_key = (os.environ.get("SHOPWARE_INTEGRATION_SECRET_KEY") or "").strip()
    if local:
        shop_url = shop_url or "http://shopware.local"
        return ShopwareSettings(
            shop_url=shop_url,
            operator=os.environ.get("MERCHANT_OPERATOR") or "Operator",
            store_name=os.environ.get("SHOPWARE_STORE_NAME") or "Local Shopware",
            low_stock_default=int(os.environ.get("SHOPWARE_LOW_STOCK_DEFAULT") or 8),
            local_store=True,
        )
    if not shop_url or not ((username and password) or (access_key and secret_key)):
        raise MissingCredentials(
            "Set SHOPWARE_URL and either SHOPWARE_ADMIN_USERNAME/PASSWORD or "
            "SHOPWARE_INTEGRATION_ACCESS_KEY/SECRET_KEY, or SHOPWARE_LOCAL_STORE=1 "
            "for the in-process catalog (no live writes)."
        )
    return ShopwareSettings(
        shop_url=shop_url.rstrip("/"),
        username=username,
        password=password,
        access_key=access_key,
        secret_key=secret_key,
        operator=os.environ.get("MERCHANT_OPERATOR") or "Operator",
        store_name=os.environ.get("SHOPWARE_STORE_NAME") or "Shopware",
        low_stock_default=int(os.environ.get("SHOPWARE_LOW_STOCK_DEFAULT") or 8),
        local_store=False,
    )


def build_merchant_config(store_name: str) -> MerchantAgentConfig:
    return MerchantAgentConfig(
        brand_name=store_name,
        require_host_approval=host_approval_default(),
        approval_surface="POST /api/merchant/changes/{id}/apply",
        enable_analysis=False,
    )
