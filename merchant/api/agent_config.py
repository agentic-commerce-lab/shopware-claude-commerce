# Copyright 2026 shopware AG
# SPDX-License-Identifier: MIT

"""Merchant settings and agent config. Credentials stay in this module.

The host authenticates as a Shopware *integration* (``SHOPWARE_INTEGRATION_ACCESS_KEY`` /
``SHOPWARE_INTEGRATION_SECRET_KEY``, OAuth ``client_credentials``); the admin user's
password grant is not accepted here (ADR-14) — scripts that bootstrap an integration
use it directly through ``admin_client.OAuthTokenProvider``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from demo_common import host_approval_default
from merchant_agent import MerchantAgentConfig

EXAMPLE_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = EXAMPLE_ROOT / "data"
SKILLS_DIR = EXAMPLE_ROOT.parent / "vendor" / "skills" / "merchant"
DEFAULT_TRANSPORT = "mcp"
TRANSPORTS = ("mcp", "rest")
DEFAULT_LOW_STOCK = 8
DEFAULT_LEDGER_DSN = "sqlite:///./merchant/data/ledger.db"


class MissingCredentials(RuntimeError):
    pass


@dataclass(frozen=True)
class ShopwareSettings:
    shop_url: str
    access_key: str = field(repr=False, default="")
    secret_key: str = field(repr=False, default="")
    transport: str = DEFAULT_TRANSPORT
    sales_channel_id: str = ""
    operator: str = "Operator"
    store_name: str | None = None
    low_stock_default: int = DEFAULT_LOW_STOCK
    local_store: bool = False
    ledger_dsn: str = DEFAULT_LEDGER_DSN

    @property
    def merchant_id(self) -> str:
        return self.shop_url


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def local_store_requested() -> bool:
    return _env("SHOPWARE_LOCAL_STORE", "0") not in {"", "0", "false"}


def load_settings() -> ShopwareSettings:
    local = local_store_requested()
    shop_url = _env("SHOPWARE_ADMIN_URL") or _env("SHOPWARE_URL")
    access_key = _env("SHOPWARE_INTEGRATION_ACCESS_KEY")
    secret_key = _env("SHOPWARE_INTEGRATION_SECRET_KEY")
    transport = _env("SHOPWARE_ADMIN_TRANSPORT", DEFAULT_TRANSPORT).lower()
    if transport not in TRANSPORTS:
        raise MissingCredentials(
            f"SHOPWARE_ADMIN_TRANSPORT={transport!r} is not one of {', '.join(TRANSPORTS)}"
        )
    common = {
        "transport": transport,
        "sales_channel_id": _env("SHOPWARE_SALES_CHANNEL_ID"),
        "operator": _env("MERCHANT_OPERATOR") or "Operator",
        "low_stock_default": int(_env("SHOPWARE_LOW_STOCK_DEFAULT") or DEFAULT_LOW_STOCK),
        "ledger_dsn": _env("MERCHANT_LEDGER_DSN") or DEFAULT_LEDGER_DSN,
    }
    if local:
        return ShopwareSettings(
            shop_url=shop_url or "http://shopware.local",
            store_name=_env("SHOPWARE_STORE_NAME") or "Local Shopware",
            local_store=True,
            **common,
        )
    if not shop_url or not (access_key and secret_key):
        raise MissingCredentials(
            "Set SHOPWARE_URL and the integration credentials SHOPWARE_INTEGRATION_ACCESS_KEY / "
            "SHOPWARE_INTEGRATION_SECRET_KEY (docker/bootstrap.sh writes them to "
            "docker/.generated.env), or SHOPWARE_LOCAL_STORE=1 for the in-process catalog "
            "(no live writes). The admin user's password is not accepted by the merchant host."
        )
    return ShopwareSettings(
        shop_url=shop_url.rstrip("/"),
        access_key=access_key,
        secret_key=secret_key,
        store_name=_env("SHOPWARE_STORE_NAME") or None,
        local_store=False,
        **common,
    )


def build_merchant_config(store_name: str) -> MerchantAgentConfig:
    return MerchantAgentConfig(
        brand_name=store_name,
        require_host_approval=host_approval_default(),
        approval_surface="POST /api/merchant/changes/{id}/apply",
        enable_analysis=False,
    )
