# Copyright 2026 shopware AG
# SPDX-License-Identifier: MIT

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
    "shipping_hint": "zzgl. Versandkosten, berechnet im Checkout; Details unter „Versand & Lieferzeit“.",
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
        unit_name = reference.get("unitName") or reference.get("referenceUnit") or "1 Einheit"
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
        rows.append(
            DisclosureRow(
                label=copy["delivery_label"],
                value=delivery_text(str(delivery_name), delivery.get("min"), delivery.get("max")),
            )
        )
    available = product.get("available")
    stock = _stock_level(product)
    if available is False or (stock is not None and stock <= 0):
        rows.append(DisclosureRow(label=copy["stock_label"], value="Derzeit nicht lieferbar"))
    elif stock is not None:
        rows.append(
            DisclosureRow(
                label=copy["stock_label"], value="Auf Lager" if stock > 0 else "Nicht auf Lager"
            )
        )
    rows.append(DisclosureRow(label="Preis", value=copy["vat"]))
    rows.append(DisclosureRow(label="Versand", value=copy["shipping_hint"]))
    return Disclosure(
        title=copy["title"], product_id=product_id, rows=rows, sources=["shopware-store-api"]
    )


def delivery_text(name: str, min_days: Any, max_days: Any) -> str:
    """The delivery-time row. Shopware's delivery-time names usually spell the range
    already ("2–4 Tage", "1-3 Werktage"); the numeric range is appended only when the
    name does not carry both bounds, so the row never reads "2–4 Tage (2–4 Tage)"."""
    if min_days is None or max_days is None:
        return name
    if str(min_days) in name and str(max_days) in name:
        return name
    return f"{name} ({min_days}–{max_days} Tage)"


def _stock_level(product: dict[str, Any]) -> int | None:
    """``availableStock`` when the record carries it (0 is a real value and means sold
    out), else ``stock``; ``None`` when neither is present."""
    for key in ("availableStock", "stock"):
        value = product.get(key)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
    return None


def _format_eur(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    formatted = f"{number:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{formatted} €"
