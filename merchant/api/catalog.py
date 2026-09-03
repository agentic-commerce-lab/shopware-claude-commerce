# Copyright 2026 Shopware × Claude Commerce Agents authors.
# SPDX-License-Identifier: Apache-2.0

"""Admin product records → merchant Listing types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from merchant_agent import Listing, ListingDetails

from .admin_client import AdminTransport


def _attrs(row: dict[str, Any]) -> dict[str, Any]:
    if "attributes" in row and isinstance(row["attributes"], dict):
        return {**row["attributes"], "id": row.get("id")}
    return row


def _price(attrs: dict[str, Any]) -> float:
    price = attrs.get("price") or []
    if isinstance(price, list) and price:
        try:
            return float(price[0].get("gross") or 0)
        except (TypeError, ValueError, AttributeError):
            return 0.0
    return 0.0


def _status(attrs: dict[str, Any]) -> str:
    if attrs.get("active") is False:
        return "paused"
    stock = int(attrs.get("availableStock") or attrs.get("stock") or 0)
    if stock <= 0:
        return "out_of_stock"
    return "active"


def _content_quality(description: str | None) -> str:
    text = (description or "").strip()
    if len(text) >= 120:
        return "good"
    if len(text) >= 40:
        return "needs_work"
    return "poor"


@dataclass
class ProductRecord:
    listing_id: str
    title: str
    product_number: str
    price: float
    stock: int
    active: bool
    parent_id: str | None
    description: str | None
    category: str | None = None
    currency: str = "EUR"
    children: list[ProductRecord] = field(default_factory=list)

    @property
    def status(self) -> str:
        return _status(
            {"active": self.active, "stock": self.stock, "availableStock": self.stock}
        )

    def to_listing(self) -> Listing:
        options: dict[str, list[str]] = {}
        if self.children:
            options["Variant"] = [c.product_number for c in self.children]
        return Listing(
            listing_id=self.listing_id,
            title=self.title,
            status=self.status,  # type: ignore[arg-type]
            price=min((c.price for c in self.children), default=self.price) if self.children else self.price,
            currency=self.currency,
            stock=sum(c.stock for c in self.children) if self.children else self.stock,
            category=self.category,
            content_quality=_content_quality(self.description),  # type: ignore[arg-type]
            short_description=(self.description or "")[:160] or None,
            options=options,
        )

    def to_details(self) -> ListingDetails:
        listing = self.to_listing()
        variants = [
            Listing(
                listing_id=child.listing_id,
                title=child.title,
                status=child.status,  # type: ignore[arg-type]
                price=child.price,
                currency=child.currency,
                stock=child.stock,
                variant_of=self.listing_id,
                option_values={"sku": child.product_number},
            )
            for child in self.children
        ]
        return ListingDetails(
            **listing.model_dump(),
            long_description=self.description,
            missing_attributes=[] if self.description else ["description"],
            variants=variants,
        )


class CatalogCache:
    def __init__(self, admin: AdminTransport) -> None:
        self._admin = admin
        self._by_id: dict[str, ProductRecord] = {}

    def cached(self) -> list[ProductRecord]:
        return [r for r in self._by_id.values() if r.parent_id is None]

    def get_cached(self, listing_id: str) -> ProductRecord | None:
        return self._by_id.get(listing_id)

    async def refresh(self) -> list[ProductRecord]:
        body = await self._admin.search(
            "product",
            {
                "limit": 100,
                "includes": {
                    "product": [
                        "id",
                        "name",
                        "productNumber",
                        "stock",
                        "availableStock",
                        "active",
                        "price",
                        "parentId",
                        "description",
                    ]
                },
            },
        )
        rows = [_record(row) for row in body.get("data") or []]
        self._by_id = {row.listing_id: row for row in rows}
        for row in rows:
            if row.parent_id and row.parent_id in self._by_id:
                parent = self._by_id[row.parent_id]
                parent.children = [c for c in parent.children if c.listing_id != row.listing_id]
                parent.children.append(row)
        return self.cached()

    async def get(self, listing_id: str) -> ProductRecord | None:
        if listing_id not in self._by_id:
            await self.refresh()
        return self._by_id.get(listing_id)

    def all_listings(self) -> list:
        return [row.to_listing() for row in self.cached()]


def _record(row: dict[str, Any]) -> ProductRecord:
    attrs = _attrs(row)
    return ProductRecord(
        listing_id=str(row.get("id") or attrs.get("id")),
        title=str(attrs.get("name") or attrs.get("translated", {}).get("name") or attrs.get("id")),
        product_number=str(attrs.get("productNumber") or ""),
        price=_price(attrs),
        stock=int(attrs.get("availableStock") or attrs.get("stock") or 0),
        active=bool(attrs.get("active", True)),
        parent_id=attrs.get("parentId"),
        description=attrs.get("description")
        or (attrs.get("translated") or {}).get("description"),
    )
