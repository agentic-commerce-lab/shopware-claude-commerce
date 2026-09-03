# Copyright 2026 Shopware × Claude Commerce Agents authors.
# SPDX-License-Identifier: Apache-2.0

"""In-process Admin API stand-in for tests and SHOPWARE_LOCAL_STORE=1."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

EUR = "b7d2554b0ce847cd82f3ac9bd1c0dfca"
SHIRT = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1"
SHIRT_S = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb1"
OIL = "ccccccccccccccccccccccccccccccc1"


def _product(
    listing_id: str,
    name: str,
    number: str,
    price: float,
    stock: int,
    *,
    parent_id: str | None = None,
    description: str = "",
    active: bool = True,
) -> dict[str, Any]:
    return {
        "id": listing_id,
        "name": name,
        "productNumber": number,
        "stock": stock,
        "availableStock": stock,
        "active": active,
        "parentId": parent_id,
        "description": description,
        "price": [{"currencyId": EUR, "gross": price, "net": round(price / 1.19, 2), "linked": True}],
    }


DEFAULT_SEED = [
    _product(SHIRT, "Claude Commerce T-Shirt", "CA-TSHIRT", 29.99, 0, description="Organic cotton T-shirt in three sizes."),
    _product(SHIRT_S, "Claude Commerce T-Shirt — S", "CA-TSHIRT-S", 29.99, 4, parent_id=SHIRT, description="Size S"),
    _product(OIL, "Extra Virgin Olive Oil 500 ml", "CA-OIL", 12.90, 40, description="Cold-pressed olive oil with Grundpreis."),
]


class FakeAdmin:
    def __init__(self, products: list[dict[str, Any]] | None = None) -> None:
        self._products = {row["id"]: deepcopy(row) for row in (products or DEFAULT_SEED)}
        self._orders = [
            {
                "id": "o1",
                "orderNumber": "10001",
                "amountTotal": 42.89,
                "orderDateTime": "2026-09-01T10:00:00.000+00:00",
            }
        ]
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    @classmethod
    def from_seed(cls, path: Path) -> FakeAdmin:
        if not path.exists():
            return cls()
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls(raw.get("products") or DEFAULT_SEED)

    async def aclose(self) -> None:
        return None

    async def search(self, entity: str, body: dict[str, Any]) -> dict[str, Any]:
        if entity == "order":
            return {"data": deepcopy(self._orders)}
        return {"data": [deepcopy(p) for p in self._products.values()]}

    async def get(self, entity: str, entity_id: str) -> dict[str, Any]:
        product = self._products.get(entity_id)
        if product is None:
            return {"data": None}
        return {"data": deepcopy(product)}

    async def patch(
        self, entity: str, entity_id: str, payload: dict[str, Any], *, dry_run: bool = False
    ) -> dict[str, Any]:
        self.calls.append(("PATCH", f"{entity}/{entity_id}", deepcopy(payload)))
        if dry_run:
            return {"dryRun": True, "payload": payload}
        product = self._products.get(entity_id)
        if product is None:
            from .admin_client import AdminAPIError

            raise AdminAPIError(f"unknown {entity} {entity_id}")
        product.update(payload)
        if "price" in payload and payload["price"]:
            product["price"] = payload["price"]
        if "stock" in payload:
            product["stock"] = int(payload["stock"])
            product["availableStock"] = int(payload["stock"])
        if "active" in payload:
            product["active"] = bool(payload["active"])
        return {"data": deepcopy(product)}
