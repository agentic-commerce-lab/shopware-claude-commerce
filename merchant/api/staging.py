# Copyright 2026 Shopware × Claude Commerce Agents authors.
# SPDX-License-Identifier: Apache-2.0

"""Apply approved ledger entries to Shopware. Staging never imports this for writes —
only ``apply_change`` reaches ``ShopwareWriter.apply``."""

from __future__ import annotations

from dataclasses import dataclass

from merchant_agent import ChangeItem, ChangeKind, StagedChange
from merchant_agent.changes import ChangeNotApplicable

from .admin_client import EUR_CURRENCY_ID, AdminAPIError, AdminTransport
from .catalog import CatalogCache, ProductRecord

LISTING_FIELDS = {
    "title": "name",
    "name": "name",
    "description": "description",
    "short_description": "description",
    "long_description": "description",
    "seo_title": "metaTitle",
    "seo_description": "metaDescription",
}

_LEDGER_ONLY = {
    ChangeKind.PROMOTION: (
        "recorded in the change ledger only — creating a live Shopware promotion "
        "needs discount rules this first version does not write"
    ),
    ChangeKind.CAMPAIGN: (
        "recorded in the change ledger only — marketing campaigns are not applied "
        "to Shopware in this deployment"
    ),
}


class WriteFailed(RuntimeError):
    def __init__(self, message: str, completed: list[str] | None = None) -> None:
        self.completed = completed or []
        super().__init__(message)


@dataclass
class ShopwareWriter:
    admin: AdminTransport
    catalog: CatalogCache

    async def apply(self, change: StagedChange) -> list[str]:
        if (note := _LEDGER_ONLY.get(change.kind)) is not None:
            return [note]
        notes: list[str] = []
        completed: list[str] = []
        for target, items in _by_target(change.items).items():
            record = await self.catalog.get(target)
            if record is None:
                raise WriteFailed(f"listing {target} is no longer in the catalog", completed)
            try:
                notes.extend(await self._write(change.kind, record, items))
            except AdminAPIError as error:
                raise WriteFailed(str(error), completed) from error
            completed.append(record.title)
        await self.catalog.refresh()
        return notes

    async def _write(
        self, kind: ChangeKind, record: ProductRecord, items: list[ChangeItem]
    ) -> list[str]:
        if kind is ChangeKind.LISTING_UPDATE:
            payload: dict = {}
            for item in items:
                field = LISTING_FIELDS.get(item.field)
                if field is None:
                    raise ChangeNotApplicable(
                        f"field {item.field!r} is not writable as a listing update"
                    )
                payload[field] = item.after
            await self.admin.patch("product", record.listing_id, payload)
            return [f"updated {', '.join(payload)} on {record.title}"]
        if kind is ChangeKind.PRICE_UPDATE:
            for item in items:
                gross = float(item.after)
                await self.admin.patch(
                    "product",
                    record.listing_id,
                    {
                        "price": [
                            {
                                "currencyId": EUR_CURRENCY_ID,
                                "gross": gross,
                                "net": round(gross / 1.19, 2),
                                "linked": True,
                            }
                        ]
                    },
                )
            return [f"price → {items[0].after} on {record.title}"]
        if kind is ChangeKind.INVENTORY_ACTION:
            payload = {}
            for item in items:
                if item.field == "stock":
                    payload["stock"] = int(item.after)
                elif item.field == "status" and item.after == "paused":
                    payload["active"] = False
                elif item.field == "status" and item.after == "active":
                    payload["active"] = True
            await self.admin.patch("product", record.listing_id, payload)
            return [f"inventory/status on {record.title}"]
        raise ChangeNotApplicable(f"{kind.value} changes are not applied by this deployment")


def _by_target(items: list[ChangeItem]) -> dict[str, list[ChangeItem]]:
    grouped: dict[str, list[ChangeItem]] = {}
    for item in items:
        grouped.setdefault(item.target, []).append(item)
    return grouped
