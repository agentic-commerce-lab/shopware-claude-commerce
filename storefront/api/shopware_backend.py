# Copyright 2026 Shopware × Claude Commerce Agents authors.
# SPDX-License-Identifier: Apache-2.0

"""``StorefrontBackend`` over a live Shopware shop.

Catalog and cart go through UCP (REST ``/ucp/v1/*``, MCP fallback). Policies,
disclosures, fulfillment, and variant enrichment use the Store API when the
UCP document is thin. Checkout is a handoff: ``create_checkout`` stages a
session and the host opens ``continue_url``. ``complete_checkout`` is never
called unless ``SHOPWARE_AGENT_COMPLETE_CHECKOUT=1`` (documented opt-in; default off).

Shopware's UCP cart id is the Store API context token (``sw-context-token``).
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

import httpx
from shopping_agent import (
    Cart,
    CartItem,
    CheckoutHandoff,
    Disclosure,
    FulfillmentOption,
    Order,
    OrderItem,
    OrderStatus,
    Policy,
    Product,
    ProductDetails,
    SearchFilters,
    ShoppingSessionContext,
    StorefrontBackend,
    Unavailable,
    UserPreferences,
)

from .disclosures import disclosure_from_store_product
from .policies import PolicyIndex
from .store_api import StoreApiClient
from .ucp_client import UcpCartGoneError, UcpClient, UcpError

logger = logging.getLogger(__name__)

_CONTEXT = {"address_country": "DE", "language": "de"}
_TAG = re.compile(r"<[^>]+>")
_EVENT_STATUS = {
    "shipped": OrderStatus.SHIPPED,
    "in_transit": OrderStatus.SHIPPED,
    "out_for_delivery": OrderStatus.OUT_FOR_DELIVERY,
    "delivered": OrderStatus.DELIVERED,
    "picked_up": OrderStatus.DELIVERED,
}
_ADJUSTMENT_STATUS = {
    "cancellation": OrderStatus.CANCELLED,
    "return": OrderStatus.RETURN_INITIATED,
    "refund": OrderStatus.REFUNDED,
}


def complete_checkout_enabled() -> bool:
    return os.environ.get("SHOPWARE_AGENT_COMPLETE_CHECKOUT", "0") == "1"


def _strip_html(value: Any) -> str | None:
    html = (value or {}).get("html") if isinstance(value, dict) else value
    if isinstance(value, dict) and not html:
        html = value.get("plain")
    if not html:
        return None
    return re.sub(r"\s+", " ", _TAG.sub(" ", str(html))).strip() or None


def _money(value: Any, default_currency: str = "EUR") -> tuple[float, str]:
    """UCP money is minor units; Shopware adapters sometimes emit major floats."""
    if isinstance(value, dict):
        amount = value.get("amount", 0)
        currency = value.get("currency") or default_currency
        if isinstance(amount, int):
            return round(amount / 100, 2), currency
        return round(float(amount or 0), 2), currency
    if isinstance(value, (int, float)):
        if isinstance(value, int) and abs(value) >= 100:
            return round(value / 100, 2), default_currency
        return round(float(value), 2), default_currency
    return 0.0, default_currency


def _image(record: dict[str, Any]) -> str | None:
    if record.get("image_url"):
        return record["image_url"]
    cover = record.get("cover") or {}
    media = cover.get("media") or cover
    if media.get("url"):
        return media["url"]
    for media in record.get("media") or []:
        if isinstance(media, dict) and (media.get("type") == "image" or media.get("url")):
            return media.get("url")
    return None


def _record_id(record: dict[str, Any]) -> str:
    return str(record.get("id") or record.get("product_id") or "")


@dataclass
class _SessionState:
    cart_id: str | None = None
    checkout_url: str | None = None
    currency: str = "EUR"
    default_variant: dict[str, str] = field(default_factory=dict)
    lines: dict[str, tuple[str, int]] = field(default_factory=dict)
    variant_of: dict[str, str] = field(default_factory=dict)
    checkout_id: str | None = None
    checkout_handoff_url: str | None = None
    order_of_checkout: dict[str, str] = field(default_factory=dict)
    order_seen_at: dict[str, datetime] = field(default_factory=dict)


class ShopwareStorefrontBackend(StorefrontBackend):
    def __init__(
        self,
        client: UcpClient | None = None,
        store_api: StoreApiClient | None = None,
        store_name: str = "Shopware",
        policies: PolicyIndex | None = None,
    ) -> None:
        self.client = client or UcpClient()
        self.store_api = store_api or StoreApiClient(self.client.shop_url)
        self.store_name = store_name
        self.policies = policies or PolicyIndex(self.store_api)
        self.products: dict[str, ProductDetails] = {}
        self._variant_images: dict[str, str] = {}
        self.default_variants: dict[str, str] = {}
        self._sessions: dict[str, _SessionState] = {}
        self.orders_enabled = True

    def _state(self, session: ShoppingSessionContext) -> _SessionState:
        return self._sessions.setdefault(session.session_id, _SessionState())

    def reset_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def cart_id_for(self, session_id: str) -> str | None:
        state = self._sessions.get(session_id)
        return state.cart_id if state else None

    def recent_orders(self, limit: int = 6) -> list[Order]:
        return []

    async def attach_cart(self, session_id: str, cart_id: str) -> Cart | None:
        try:
            payload = await self.client.call_ucp("get_cart", {"id": cart_id})
        except UcpCartGoneError:
            return None
        except UcpError:
            return None
        state = self._sessions.setdefault(session_id, _SessionState())
        state.checkout_id = None
        state.checkout_handoff_url = None
        return self._map_cart(state, payload)

    async def checkout_url_for(self, session_id: str) -> str | None:
        state = self._sessions.get(session_id)
        if state is None:
            return None
        if state.lines and state.checkout_handoff_url is None:
            await self._stage_handoff(state)
        # Browser cannot set sw-context-token on the shop origin. The handoff
        # plugin adopts the UCP cart id (context token) then redirects to confirm.
        if state.cart_id:
            return (
                f"{self.client.shop_url}/claude-commerce/continue?token="
                f"{quote(state.cart_id, safe='')}"
            )
        return state.checkout_handoff_url or state.checkout_url

    async def search_products(
        self,
        session: ShoppingSessionContext,
        query: str,
        filters: SearchFilters | None = None,
        limit: int = 8,
    ) -> list[Product]:
        catalog: dict[str, Any] = {
            "query": query,
            "context": _CONTEXT,
            "pagination": {"limit": limit},
        }
        price: dict[str, int] = {}
        if filters and filters.min_price is not None:
            price["min"] = int(filters.min_price * 100)
        if filters and filters.max_price is not None:
            price["max"] = int(filters.max_price * 100)
        if price:
            catalog["filters"] = {"price": price}
        try:
            payload = await self.client.call_ucp("search_catalog", {"catalog": catalog})
            records = payload.get("products") or payload.get("items") or []
        except (UcpError, httpx.HTTPError) as error:
            logger.warning("UCP search failed (%s); Store API fallback", error)
            records = await self.store_api.search_products(query, limit)
        state = self._state(session)
        return [self._remember_product(state, record) for record in records if _record_id(record)]

    async def get_product_details(
        self, session: ShoppingSessionContext, product_id: str
    ) -> ProductDetails | None:
        state = self._state(session)
        parent = state.variant_of.get(product_id)
        # Shopware often emits a variants[] row whose id equals the parent.
        # That is not a child SKU — do not collapse the family to a thin Product.
        if parent is not None and parent != product_id:
            details = self.products.get(parent) or await self.get_product_details(session, parent)
            if details is None:
                return None
            for variant in details.variants:
                if variant.product_id == product_id:
                    return ProductDetails(
                        **variant.model_dump(), long_description=details.long_description
                    )
            return None
        record = await self._fetch_product_record(product_id)
        if record is None:
            store = await self.store_api.product(product_id)
            if store is None:
                return None
            record = _store_api_to_ucp(store)
        details = self._remember_product(state, record)
        await self._enrich_variants(state, details, product_id)
        return self.products.get(details.product_id, details)

    async def _fetch_product_record(self, product_id: str) -> dict[str, Any] | None:
        try:
            payload = await self.client.call_ucp(
                "get_product", {"catalog": {"id": product_id, "context": _CONTEXT}}
            )
            record = payload.get("product") or payload
            if record and _record_id(record):
                return record
        except UcpError:
            pass
        try:
            payload = await self.client.call_ucp(
                "lookup_catalog",
                {"catalog": {"ids": [product_id], "context": _CONTEXT}},
            )
        except UcpError:
            return None
        found = payload.get("products") or []
        return found[0] if found else None

    async def _enrich_variants(
        self, state: _SessionState, details: ProductDetails, product_id: str
    ) -> None:
        store = await self.store_api.product(product_id)
        if not store:
            return
        # Product detail for a parent resolves to the selected variant, so children[]
        # is empty and parentId points at the family. List variants by parentId.
        family_id = str(store.get("parentId") or store.get("id") or product_id)
        children = list(store.get("children") or [])
        if not children:
            children = await self.store_api.child_products(family_id)
        delivery = store.get("deliveryTime") or {}
        delivery_name = delivery.get("translated", {}).get("name") or delivery.get("name")
        if delivery_name:
            details.specs["deliveryTime"] = str(delivery_name)
        if not children:
            return
        parent_doc = {
            "id": family_id,
            "name": details.title,
            "translated": {"name": details.title},
            "cover": store.get("cover"),
        }
        variants = [_variant_from_store(parent_doc, child) for child in children]
        existing = {v.product_id: v for v in details.variants}
        existing.update({v.product_id: v for v in variants})
        details.variants = list(existing.values())
        options: dict[str, list[str]] = {}
        for variant in details.variants:
            for key, value in variant.option_values.items():
                options.setdefault(key, [])
                if value not in options[key]:
                    options[key].append(value)
        details.options = options
        self._remember_details(state, details)

    def _remember_product(self, state: _SessionState, record: dict[str, Any]) -> ProductDetails:
        product_id = _record_id(record)
        price, currency = _product_price(record)
        description = _strip_html(record.get("description")) or record.get("translated", {}).get(
            "description"
        )
        if isinstance(description, str):
            description = _strip_html({"html": description}) or description
        variants = [
            self._map_variant(record, variant)
            for variant in record.get("variants") or []
            if _record_id(variant) and _record_id(variant) != product_id
        ]
        existing = self.products.get(product_id)
        if existing:
            merged = {v.product_id: v for v in existing.variants}
            merged.update({v.product_id: v for v in variants})
            variants = list(merged.values())
        options = _family_options(record, variants)
        available = [v for v in variants if v.in_stock]
        details = ProductDetails(
            product_id=product_id,
            title=str(record.get("title") or record.get("translated", {}).get("name") or record.get("name") or product_id),
            price=price,
            currency=currency,
            image_url=_image(record),
            category=_category(record),
            in_stock=bool(available) if variants else _in_stock(record),
            short_description=(description[:200] if description else None),
            long_description=description if isinstance(description, str) else None,
            variants=variants,
            options=options,
            brand=_brand(record),
        )
        return self._remember_details(state, details)

    def _remember_details(self, state: _SessionState, details: ProductDetails) -> ProductDetails:
        state.currency = details.currency
        for variant in details.variants:
            if variant.product_id != details.product_id:
                state.variant_of[variant.product_id] = details.product_id
            if variant.image_url:
                self._variant_images[variant.product_id] = variant.image_url
        available = [v for v in details.variants if v.in_stock]
        if available or details.variants:
            chosen = (available or details.variants)[0].product_id
            state.default_variant[details.product_id] = chosen
            self.default_variants[details.product_id] = chosen
        self.products[details.product_id] = details
        return details

    def warm_display_cache(self, details: ProductDetails) -> None:
        self.products[details.product_id] = details
        for variant in details.variants:
            if variant.image_url:
                self._variant_images[variant.product_id] = variant.image_url
        available = [v for v in details.variants if v.in_stock]
        if available or details.variants:
            self.default_variants[details.product_id] = (available or details.variants)[0].product_id

    def _map_variant(self, record: dict[str, Any], variant: dict[str, Any]) -> Product:
        price, currency = _money(variant.get("price") or {}, record.get("currency") or "EUR")
        options = {
            opt.get("name") or "": opt.get("label") or opt.get("value") or ""
            for opt in variant.get("options") or []
            if isinstance(opt, dict)
        }
        parent_id = _record_id(record)
        variant_id = _record_id(variant) or parent_id
        title = variant.get("title") or " / ".join(options.values()) or parent_id
        return Product(
            product_id=variant_id,
            title=f"{record.get('title') or record.get('name') or parent_id} — {title}",
            price=price,
            currency=currency,
            image_url=_image(variant) or _image(record),
            attributes=options,
            option_values=options,
            variant_of=parent_id,
            in_stock=_in_stock(variant),
        )

    async def get_cart(self, session: ShoppingSessionContext) -> Cart:
        state = self._state(session)
        if state.cart_id is None:
            return Cart(currency=state.currency)
        try:
            payload = await self.client.call_ucp("get_cart", {"id": state.cart_id})
        except UcpCartGoneError:
            self._drop_cart(state)
            return Cart(currency=state.currency)
        return self._map_cart(state, payload)

    async def add_to_cart(
        self, session: ShoppingSessionContext, product_id: str, quantity: int
    ) -> Cart:
        state = self._state(session)
        variant_id = await self._resolve_variant(session, state, product_id)
        await self._assert_available(session, variant_id)
        await self._refresh_lines(state)
        already = state.lines.get(variant_id)
        line_items = self._line_items(state, variant_id, (already[1] if already else 0) + quantity)
        if state.cart_id is None:
            return await self._create_cart(state, line_items)
        try:
            payload = await self.client.call_ucp(
                "update_cart", {"id": state.cart_id, "cart": {"line_items": line_items}}
            )
        except UcpCartGoneError:
            self._drop_cart(state)
            return await self._create_cart(
                state, [{"item": {"id": variant_id}, "quantity": quantity}]
            )
        return self._map_cart_after_write(state, payload)

    async def update_cart_item(
        self, session: ShoppingSessionContext, product_id: str, quantity: int
    ) -> Cart:
        return await self._set_line(session, product_id, quantity)

    async def remove_from_cart(self, session: ShoppingSessionContext, product_id: str) -> Cart:
        return await self._set_line(session, product_id, 0)

    async def _set_line(
        self, session: ShoppingSessionContext, product_id: str, quantity: int
    ) -> Cart:
        state = self._state(session)
        await self._refresh_lines(state)
        variant_id = (
            product_id
            if product_id in state.lines
            else state.default_variant.get(product_id, product_id)
        )
        if state.cart_id is None or variant_id not in state.lines:
            return await self.get_cart(session)
        try:
            payload = await self.client.call_ucp(
                "update_cart",
                {
                    "id": state.cart_id,
                    "cart": {"line_items": self._line_items(state, variant_id, quantity)},
                },
            )
        except UcpCartGoneError:
            self._drop_cart(state)
            return Cart(currency=state.currency)
        return self._map_cart_after_write(state, payload)

    async def _create_cart(self, state: _SessionState, line_items: list[dict[str, Any]]) -> Cart:
        payload = await self.client.call_ucp(
            "create_cart", {"cart": {"line_items": line_items, "context": _CONTEXT}}
        )
        return self._map_cart_after_write(state, payload)

    def _map_cart_after_write(self, state: _SessionState, payload: dict[str, Any]) -> Cart:
        state.checkout_handoff_url = None
        return self._map_cart(state, payload)

    async def _refresh_lines(self, state: _SessionState) -> None:
        if state.cart_id is None:
            return
        try:
            payload = await self.client.call_ucp("get_cart", {"id": state.cart_id})
        except UcpCartGoneError:
            self._drop_cart(state)
            return
        self._map_cart(state, payload)

    def _line_items(
        self, state: _SessionState, variant_id: str, quantity: int
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for vid, (line_id, qty) in state.lines.items():
            if vid == variant_id and quantity <= 0:
                continue
            items.append(
                {
                    "id": line_id,
                    "item": {"id": vid},
                    "quantity": quantity if vid == variant_id else qty,
                }
            )
        if variant_id not in state.lines and quantity > 0:
            items.append({"item": {"id": variant_id}, "quantity": quantity})
        return items

    def _drop_cart(self, state: _SessionState) -> None:
        state.cart_id = None
        state.checkout_url = None
        state.checkout_handoff_url = None
        state.lines = {}

    async def _resolve_variant(
        self, session: ShoppingSessionContext, state: _SessionState, product_id: str
    ) -> str:
        details = self.products.get(product_id)
        if details and details.variants:
            if product_id not in state.default_variant:
                await self.get_product_details(session, product_id)
        if product_id in state.lines:
            return product_id
        if product_id in state.variant_of:
            return product_id
        if product_id not in state.default_variant and product_id not in self.default_variants:
            await self.get_product_details(session, product_id)
        variant_id = state.default_variant.get(product_id) or self.default_variants.get(product_id)
        if variant_id is None:
            return product_id
        return variant_id

    async def _assert_available(self, session: ShoppingSessionContext, variant_id: str) -> None:
        details = self.products.get(variant_id)
        parent_id = None
        for product in self.products.values():
            for variant in product.variants:
                if variant.product_id == variant_id:
                    details = product
                    parent_id = product.product_id
                    if not variant.in_stock:
                        siblings = [
                            v.product_id for v in product.variants if v.in_stock
                        ]
                        raise Unavailable(
                            f"{variant_id} is unavailable"
                            + (f"; in stock: {', '.join(siblings)}" if siblings else "")
                        )
                    return
        if details is not None and details.in_stock is False and not details.variants:
            raise Unavailable(f"{variant_id} is unavailable")
        _ = session, parent_id

    def _map_cart(self, state: _SessionState, cart: dict[str, Any]) -> Cart:
        state.cart_id = str(cart.get("id") or state.cart_id)
        state.checkout_url = cart.get("continue_url") or state.checkout_url
        if not state.checkout_url:
            links = cart.get("links") or []
            for link in links:
                if isinstance(link, dict) and link.get("rel") in {"continue", "checkout"}:
                    state.checkout_url = link.get("href")
        state.lines = {}
        items: list[CartItem] = []
        currency = cart.get("currency") or state.currency
        for line in cart.get("line_items") or []:
            item = line.get("item") or {}
            variant_id = str(item.get("id") or "")
            extra = item.get("extra") or line.get("extra") or {}
            line_id = str(line.get("id") or extra.get("line_item_id") or variant_id)
            quantity = int(line.get("quantity") or 1)
            state.lines[variant_id] = (line_id, quantity)
            price, line_currency = _money(item.get("price"), currency)
            currency = line_currency or currency
            items.append(
                CartItem(
                    product_id=variant_id,
                    title=str(item.get("title") or variant_id),
                    price=price,
                    quantity=quantity,
                    image_url=item.get("image_url") or self._variant_images.get(variant_id),
                )
            )
        state.currency = currency
        return Cart(items=items, currency=currency)

    async def _stage_handoff(self, state: _SessionState) -> None:
        line_items = [
            {"item": {"id": vid}, "quantity": qty} for vid, (_, qty) in state.lines.items()
        ]
        try:
            document = await self._stage_checkout(state, line_items)
        except UcpError:
            logger.warning("checkout staging failed; handing off the cart's own link")
            return
        state.checkout_id = document.get("id") or state.checkout_id
        continue_url = document.get("continue_url")
        if not continue_url:
            for link in document.get("links") or []:
                if isinstance(link, dict) and link.get("rel") == "continue":
                    continue_url = link.get("href")
        state.checkout_handoff_url = continue_url or state.checkout_handoff_url

    async def _stage_checkout(
        self, state: _SessionState, line_items: list[dict[str, Any]]
    ) -> dict[str, Any]:
        checkout: dict[str, Any] = {"line_items": line_items}
        if state.cart_id:
            checkout["cart_id"] = state.cart_id
        if state.checkout_id is not None:
            try:
                return await self.client.call_ucp(
                    "update_checkout",
                    {"id": state.checkout_id, "checkout": checkout},
                    document_error_ok=True,
                )
            except UcpError:
                state.checkout_id = None
        return await self.client.call_ucp(
            "create_checkout", {"checkout": checkout}, document_error_ok=True
        )

    async def checkout_handoff(
        self, session: ShoppingSessionContext, cart: Cart
    ) -> list[CheckoutHandoff]:
        url = await self.checkout_url_for(session.session_id)
        if not url or not cart.items:
            return []
        return [CheckoutHandoff(url=url, label="Checkout in Shopware")]

    async def get_preferences(self, session: ShoppingSessionContext) -> UserPreferences:
        return UserPreferences(
            user_id=session.user_id,
            display_name="Guest",
            default_location="DE",
            preferences={"language": "de", "currency": "EUR"},
        )

    async def get_orders(self, session: ShoppingSessionContext, limit: int = 5) -> list[Order]:
        state = self._state(session)
        await self._sync_ledger(state)
        order_ids = list(state.order_of_checkout.values())[-limit:]
        orders = []
        for order_id in reversed(order_ids):
            order = await self._fetch_order(state, order_id)
            if order is not None:
                orders.append(order)
        return orders

    async def get_order(self, session: ShoppingSessionContext, order_id: str) -> Order | None:
        state = self._state(session)
        await self._sync_ledger(state)
        if order_id not in state.order_of_checkout.values():
            return None
        return await self._fetch_order(state, order_id)

    async def _sync_ledger(self, state: _SessionState) -> None:
        if state.checkout_id is None or state.checkout_id in state.order_of_checkout:
            return
        try:
            document = await self.client.call_ucp(
                "get_checkout", {"id": state.checkout_id}, document_error_ok=True
            )
        except UcpError:
            return
        order_id = (document.get("order") or {}).get("id")
        if order_id:
            state.order_of_checkout[state.checkout_id] = order_id
            state.order_seen_at.setdefault(order_id, datetime.now(UTC))

    async def _fetch_order(self, state: _SessionState, order_id: str) -> Order | None:
        try:
            document = await self.client.call_ucp("get_order", {"id": order_id})
        except UcpError:
            return None
        return self._map_order(state, document)

    def _map_order(self, state: _SessionState, document: dict[str, Any]) -> Order:
        order_id = str(document["id"])
        timeline: list[tuple[str, OrderStatus | None]] = []
        events = (document.get("fulfillment") or {}).get("events") or []
        for event in events:
            timeline.append((event.get("occurred_at") or "", _EVENT_STATUS.get(event.get("type"))))
        for adjustment in document.get("adjustments") or []:
            status = _ADJUSTMENT_STATUS.get(adjustment.get("type"))
            timeline.append((adjustment.get("occurred_at") or "", status))
        timeline.sort(key=lambda entry: entry[0])
        statuses = [status for _, status in timeline if status is not None]
        items = []
        for line in document.get("line_items") or []:
            item = line.get("item") or {}
            quantity = line.get("quantity") or {}
            qty = quantity.get("total") if isinstance(quantity, dict) else quantity
            price, _ = _money(item.get("price"), document.get("currency") or state.currency)
            items.append(
                OrderItem(
                    product_id=str(item.get("id") or ""),
                    title=str(item.get("title") or item.get("id") or "item"),
                    quantity=int(qty or 1),
                    price=price,
                )
            )
        total = 0.0
        for row in document.get("totals") or []:
            if row.get("type") == "total":
                total, _ = _money(row, document.get("currency") or state.currency)
                if "amount" in row and not isinstance(row.get("amount"), dict):
                    total, _ = _money({"amount": row["amount"], "currency": document.get("currency")}, document.get("currency") or "EUR")
        tracked = [e for e in events if e.get("tracking_url")]
        placed_at = state.order_seen_at.get(order_id, datetime.now(UTC))
        return Order(
            order_id=order_id,
            status=statuses[-1] if statuses else OrderStatus.PROCESSING,
            placed_at=placed_at,
            items=items,
            total=total,
            currency=document.get("currency") or state.currency,
            tracking_url=tracked[-1]["tracking_url"] if tracked else None,
        )

    async def search_policies(self, session: ShoppingSessionContext, query: str) -> list[Policy]:
        return await self.policies.search(session, query)

    async def get_disclosure(
        self, session: ShoppingSessionContext, product_id: str
    ) -> Disclosure | None:
        product = await self.store_api.product(product_id)
        if not product:
            parent = self._state(session).variant_of.get(product_id)
            if parent:
                product = await self.store_api.product(parent)
        if not product:
            return None
        return disclosure_from_store_product(product_id, product)

    async def get_fulfillment_options(
        self, session: ShoppingSessionContext, product_ids: list[str]
    ) -> list[FulfillmentOption]:
        methods = await self.store_api.shipping_methods(self.cart_id_for(session.session_id))
        options: list[FulfillmentOption] = []
        eta = "siehe Produkt-Lieferzeit"
        if product_ids:
            details = self.products.get(product_ids[0])
            if details and details.specs.get("deliveryTime"):
                eta = details.specs["deliveryTime"]
        for method in methods:
            name = (
                method.get("translated", {}).get("name")
                or method.get("name")
                or "Versand"
            )
            price = 0.0
            prices = method.get("prices") or []
            if prices:
                try:
                    price = float((prices[0].get("currencyPrice") or [{}])[0].get("gross") or 0)
                except (TypeError, ValueError, IndexError):
                    price = 0.0
            options.append(
                FulfillmentOption(method="shipping", eta=f"{name}: {eta}", fee=price)
            )
        return options


def _product_price(record: dict[str, Any]) -> tuple[float, str]:
    if record.get("price_range"):
        return _money((record["price_range"].get("min") or record["price_range"]), record.get("currency") or "EUR")
    if record.get("calculatedPrice"):
        return round(float(record["calculatedPrice"].get("unitPrice") or 0), 2), "EUR"
    if "price" in record:
        return _money(record["price"], record.get("currency") or "EUR")
    return 0.0, record.get("currency") or "EUR"


def _in_stock(record: dict[str, Any]) -> bool:
    availability = record.get("availability") or {}
    if "available" in availability:
        return bool(availability["available"])
    if "available" in record:
        return bool(record["available"])
    stock = record.get("availableStock", record.get("stock"))
    if stock is None:
        return True
    return int(stock) > 0


def _category(record: dict[str, Any]) -> str | None:
    tags = record.get("tags") or []
    if tags:
        first = tags[0]
        return first if isinstance(first, str) else str(first.get("name") or first)
    categories = record.get("categories") or []
    if categories:
        first = categories[0]
        if isinstance(first, dict):
            return first.get("translated", {}).get("name") or first.get("name")
    return None


def _brand(record: dict[str, Any]) -> str | None:
    manufacturer = record.get("manufacturer") or {}
    if isinstance(manufacturer, dict):
        return manufacturer.get("translated", {}).get("name") or manufacturer.get("name")
    return None


def _family_options(record: dict[str, Any], variants: list[Product]) -> dict[str, list[str]]:
    options: dict[str, list[str]] = {}
    for spec in record.get("options") or []:
        if isinstance(spec, dict) and spec.get("name"):
            values = []
            for value in spec.get("values") or []:
                if isinstance(value, dict):
                    values.append(str(value.get("label") or value.get("name") or ""))
                else:
                    values.append(str(value))
            options[str(spec["name"])] = [v for v in values if v]
    if options:
        return options
    for variant in variants:
        for key, value in variant.option_values.items():
            options.setdefault(key, [])
            if value not in options[key]:
                options[key].append(value)
    return options


def _store_api_to_ucp(product: dict[str, Any]) -> dict[str, Any]:
    name = product.get("translated", {}).get("name") or product.get("name")
    description = product.get("translated", {}).get("description") or product.get("description")
    price = (product.get("calculatedPrice") or {}).get("unitPrice")
    return {
        "id": product.get("id"),
        "title": name,
        "name": name,
        "description": {"html": description} if description else None,
        "price": price,
        "currency": "EUR",
        "media": [{"type": "image", "url": ((product.get("cover") or {}).get("media") or {}).get("url")}],
        "available": product.get("available", True),
        "categories": product.get("categories") or [],
        "manufacturer": product.get("manufacturer"),
        "variants": [
            {
                "id": child.get("id"),
                "title": child.get("translated", {}).get("name") or child.get("name"),
                "price": {"amount": int(round(float((child.get("calculatedPrice") or {}).get("unitPrice") or 0) * 100)), "currency": "EUR"},
                "availability": {"available": bool(child.get("available", (child.get("availableStock") or 0) > 0))},
                "options": [
                    {
                        "name": (opt.get("group") or {}).get("translated", {}).get("name")
                        or (opt.get("group") or {}).get("name")
                        or "Option",
                        "label": opt.get("translated", {}).get("name") or opt.get("name"),
                    }
                    for opt in child.get("options") or []
                ],
            }
            for child in product.get("children") or []
        ],
    }


def _variant_from_store(parent: dict[str, Any], child: dict[str, Any]) -> Product:
    price = float((child.get("calculatedPrice") or {}).get("unitPrice") or 0)
    options = {}
    for opt in child.get("options") or []:
        group = (opt.get("group") or {}).get("translated", {}).get("name") or (opt.get("group") or {}).get("name") or "Option"
        options[group] = opt.get("translated", {}).get("name") or opt.get("name") or ""
    title = child.get("translated", {}).get("name") or child.get("name") or " / ".join(options.values())
    parent_title = parent.get("translated", {}).get("name") or parent.get("name") or ""
    return Product(
        product_id=str(child.get("id")),
        title=f"{parent_title} — {title}" if parent_title else str(title),
        price=round(price, 2),
        currency="EUR",
        image_url=((child.get("cover") or parent.get("cover") or {}).get("media") or {}).get("url"),
        attributes=options,
        option_values=options,
        variant_of=str(parent.get("id")),
        in_stock=bool(child.get("available", (child.get("availableStock") or 0) > 0)),
    )
