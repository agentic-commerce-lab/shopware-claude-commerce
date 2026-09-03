# Copyright 2026 Shopware × Claude Commerce Agents authors.
# SPDX-License-Identifier: Apache-2.0

"""Server-authored PAngV disclosures. Copy is fixed; the model never writes these lines."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from shopping_agent import Disclosure, DisclosureRow

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
COPY_PATH = DATA_DIR / "disclosure_copy.de.json"

_DEFAULT_COPY = {
    "title": "Pflichtangaben",
    "vat": "inkl. MwSt.",
    "shipping_hint": "zzgl. Versandkosten, berechnet im Checkout.",
    "grundpreis_label": "Grundpreis",
    "delivery_label": "Lieferzeit",
    "stock_label": "Verfügbarkeit",
}


def load_copy() -> dict[str, str]:
    if COPY_PATH.exists():
        return {**_DEFAULT_COPY, **json.loads(COPY_PATH.read_text(encoding="utf-8"))}
    return dict(_DEFAULT_COPY)


def disclosure_from_store_product(product_id: str, product: dict[str, Any]) -> Disclosure:
    copy = load_copy()
    rows: list[DisclosureRow] = []
    calculated = product.get("calculatedPrice") or product.get("calculatedCheapestPrice") or {}
    reference = calculated.get("referencePrice") or product.get("referencePrice") or {}
    if reference:
        unit_price = reference.get("price") or reference.get("unitPrice")
        unit_name = (
            (reference.get("unitName") or reference.get("referenceUnit") or "1 Einheit")
        )
        if unit_price is not None:
            rows.append(
                DisclosureRow(
                    label=copy["grundpreis_label"],
                    value=f"{_format_eur(unit_price)} / {unit_name}",
                )
            )
    delivery = product.get("deliveryTime") or {}
    delivery_name = delivery.get("translated", {}).get("name") or delivery.get("name")
    if delivery_name:
        min_days = delivery.get("min")
        max_days = delivery.get("max")
        eta = delivery_name
        if min_days is not None and max_days is not None:
            eta = f"{delivery_name} ({min_days}–{max_days} Tage)"
        rows.append(DisclosureRow(label=copy["delivery_label"], value=str(eta)))
    available = product.get("available")
    stock = product.get("availableStock") or product.get("stock")
    if available is False or (stock is not None and stock <= 0):
        rows.append(DisclosureRow(label=copy["stock_label"], value="Derzeit nicht lieferbar"))
    elif stock is not None:
        rows.append(DisclosureRow(label=copy["stock_label"], value="Auf Lager" if stock > 0 else "Nicht auf Lager"))
    rows.append(DisclosureRow(label="Preis", value=copy["vat"]))
    rows.append(DisclosureRow(label="Versand", value=copy["shipping_hint"]))
    return Disclosure(title=copy["title"], product_id=product_id, rows=rows, sources=["shopware-store-api"])


def _format_eur(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    formatted = f"{number:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{formatted} €"
