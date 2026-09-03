# Copyright 2026 shopware AG
# SPDX-License-Identifier: MIT

"""``StorefrontBackend`` over a live Shopware shop.

Catalog and cart go through UCP (MCP primary, REST fallback — ADR-12). Policies,
disclosures, fulfillment, variants and order history use the Store API, which UCP does
not cover. Checkout is a **handoff** (ADR-10): the cart id *is* the Store API context
token, and the customer continues in Shopware's own checkout through a one-time signed
code minted by the host; the agent never completes a checkout and never creates UCP
checkout sessions on a read.

Variants: Shopware's UCP documents list a family (parent) with ``variants[]``; a row
whose id equals the parent is the parent itself, not a child SKU. Real children come from
the Store API (``parentId`` filter) so out-of-stock sizes are listed and refused, and a
variant id resolves to its own details from any session.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

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
from shopware_common.handoff import HandoffCode

from .disclosures import disclosure_from_store_product
from .handoff import HandoffBroker
from .policies import PolicyIndex
from .store_api import StoreApiClient, StoreApiError
from .ucp_client import UcpAuthError, UcpCartGoneError, UcpClient, UcpError

logger = logging.getLogger(__name__)

TokenProvider = Callable[[str], Awaitable[str | None]]
CustomerTokenProvider = Callable[[str], str | None]

_CONTEXT = {"address_country": "DE", "language": "de"}
_TAG = re.compile(r"<[^>]+>")
DEFAULT_CURRENCY = "EUR"
DEFAULT_ETA = "siehe Produkt-Lieferzeit"
HANDOFF_LABEL = "Checkout in Shopware"
_MINOR_UNIT_THRESHOLD = 100

_ORDER_STATE = {"cancelled": OrderStatus.CANCELLED}
_DELIVERY_STATE = {
    "shipped": OrderStatus.SHIPPED,
    "shipped_partially": OrderStatus.SHIPPED,
    "returned": OrderStatus.RETURN_INITIATED,
    "returned_partially": OrderStatus.RETURN_INITIATED,
}
_TRANSACTION_STATE = {
    "refunded": OrderStatus.REFUNDED,
    "refunded_partially": OrderStatus.REFUNDED,
}


def _strip_html(value: Any) -> str | None:
    html = (value or {}).get("html") if isinstance(value, dict) else value
    if isinstance(value, dict) and not html:
        html = value.get("plain")
    if not html:
        return None
    return re.sub(r"\s+", " ", _TAG.sub(" ", str(html))).strip() or None


def _money(value: Any, default_currency: str = DEFAULT_CURRENCY) -> tuple[float, str]:
    """UCP money is minor units; Shopware adapters sometimes emit major floats."""
    if isinstance(value, dict):
        amount = value.get("amount", 0)
        currency = value.get("currency") or default_currency
        if isinstance(amount, int):
            return round(amount / 100, 2), currency
        return round(float(amount or 0), 2), currency
    if isinstance(value, (int, float)):
        if isinstance(value, int) and abs(value) >= _MINOR_UNIT_THRESHOLD:
            return round(value / 100, 2), default_currency
        return round(float(value), 2), default_currency
    return 0.0, default_currency


def _image(record: dict[str, Any]) -> str | None:
    if record.get("image_url"):
        return record["image_url"]
    cover = record.get("cover") or {}
    media = cover.get("media") or cover
    if isinstance(media, dict) and media.get("url"):
        return media["url"]
    for media in record.get("media") or []:
        if isinstance(media, dict) and (media.get("type") == "image" or media.get("url")):
            return media.get("url")
    return None


def _record_id(record: dict[str, Any]) -> str:
    return str(record.get("id") or record.get("product_id") or "")


def _translated(record: dict[str, Any], key: str) -> Any:
    return (record.get("translated") or {}).get(key) or record.get(key)


@dataclass
class _SessionState:
    cart_id: str | None = None
    currency: str = DEFAULT_CURRENCY
    default_variant: dict[str, str] = field(default_factory=dict)
    lines: dict[str, tuple[str, int]] = field(default_factory=dict)


class ShopwareStorefrontBackend(StorefrontBackend):
    def __init__(
        self,
        client: UcpClient | None = None,
        store_api: StoreApiClient | None = None,
        store_name: str = "Shopware",
        policies: PolicyIndex | None = None,
        handoff: HandoffBroker | None = None,
        token_provider: TokenProvider | None = None,
        customer_token_provider: CustomerTokenProvider | None = None,
        on_auth_failure: Callable[[str], None] | None = None,
    ) -> None:
        self.client = client or UcpClient()
        self.store_api = store_api or StoreApiClient(self.client.shop_url)
        self.store_name = store_name
        self.policies = policies or PolicyIndex(self.store_api)
        self.handoff = handoff or HandoffBroker(self.client.shop_url)
        self._token_provider = token_provider
        self._customer_token_provider = customer_token_provider
        self._on_auth_failure = on_auth_failure
        self.products: dict[str, ProductDetails] = {}
        self.variant_of: dict[str, str] = {}
        self.default_variants: dict[str, str] = {}
        self._variant_images: dict[str, str] = {}
        self._sessions: dict[str, _SessionState] = {}

    # ------------------------------------------------------------------ sessions

    def _state(self, session: ShoppingSessionContext) -> _SessionState:
        return self._sessions.setdefault(session.session_id, _SessionState())

    def reset_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
        self.handoff.revoke(session_id)

    def cart_id_for(self, session_id: str) -> str | None:
        state = self._sessions.get(session_id)
        return state.cart_id if state else None

    def checkout_url_for(self, session_id: str) -> str | None:
        """The session-bound ticket URL on this host, or ``None`` without a cart. No
        network: nothing is created in Shopware until the customer clicks."""
        state = self._sessions.get(session_id)
        if state is None or not state.cart_id or not state.lines:
            return None
        return self.handoff.continue_url(session_id)

    def handoff_code_for(self, session_id: str) -> HandoffCode | None:
        """Mint the one-time handoff code for the session's cart (called by the host's
        ticket route at click time)."""
        state = self._sessions.get(session_id)
        if state is None or not state.cart_id or not self.handoff.configured:
            return None
        return self.handoff.mint(state.cart_id)

    async def attach_cart(self, session_id: str, cart_id: str) -> Cart | None:
        try:
            payload = await self._ucp(session_id, "get_cart", {"id": cart_id})
        except UcpError:
            return None
        state = self._sessions.setdefault(session_id, _SessionState())
        self.handoff.revoke(session_id)
        return self._map_cart(state, payload)

    async def _ucp(
        self, session_id: str, name: str, arguments: dict[str, Any], **kwargs: Any
    ) -> dict[str, Any]:
        """A UCP call with the session's buyer token when identity is linked; a rejected
        token is dropped and the call repeated as a guest."""
        bearer = await self._token_provider(session_id) if self._token_provider else None
        try:
            return await self.client.call_ucp(name, arguments, bearer_token=bearer, **kwargs)
        except UcpAuthError:
            if bearer is None:
                raise
            logger.info(
                "UCP rejected the linked token for session %s; continuing as guest", session_id
            )
            if self._on_auth_failure is not None:
                self._on_auth_failure(session_id)
            return await self.client.call_ucp(name, arguments, **kwargs)

    # ------------------------------------------------------------------ catalog

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
            price["min"] = int(round(filters.min_price * 100))
        if filters and filters.max_price is not None:
            price["max"] = int(round(filters.max_price * 100))
        if price:
            catalog["filters"] = {"price": price}
        try:
            payload = await self._ucp(session.session_id, "search_catalog", {"catalog": catalog})
            records = payload.get("products") or payload.get("items") or []
        except UcpError as error:
            logger.warning("UCP search failed (%s); Store API fallback", error)
            try:
                records = [
                    _store_api_to_ucp(p) for p in await self.store_api.search_products(query, limit)
                ]
            except StoreApiError:
                records = []
        state = self._state(session)
        products = [
            self._remember_product(state, record) for record in records if _record_id(record)
        ]
        # The MCP search tool has no price filter; the REST filter is a hint. Enforce here.
        if filters and (filters.min_price is not None or filters.max_price is not None):
            products = [p for p in products if _within_price(p, filters)]
        return products[:limit]

    async def get_product_details(
        self, session: ShoppingSessionContext, product_id: str
    ) -> ProductDetails | None:
        state = self._state(session)
        parent = self.variant_of.get(product_id)
        if parent is not None and parent != product_id:
            return await self._variant_details(session, parent, product_id)
        record, store = await self._fetch_product_record(session.session_id, product_id)
        if record is None:
            try:
                store = await self.store_api.product(product_id)
            except StoreApiError:
                store = None
            if store is None:
                return None
            record = _store_api_to_ucp(store)
        family_id = _record_id(record)
        if family_id != product_id:
            # The shop answered a lookup for a child with its family document.
            self.variant_of[product_id] = family_id
        details = self._remember_product(state, record)
        await self._enrich_variants(state, details, store)
        if family_id != product_id:
            return await self._variant_details(session, family_id, product_id)
        return self.products.get(details.product_id, details)

    async def _variant_details(
        self, session: ShoppingSessionContext, parent_id: str, variant_id: str
    ) -> ProductDetails | None:
        details = self.products.get(parent_id)
        if details is None or not details.variants:
            details = await self.get_product_details(session, parent_id)
        if details is None:
            return None
        for variant in details.variants:
            if variant.product_id == variant_id:
                return ProductDetails(
                    **variant.model_dump(),
                    long_description=details.long_description,
                    specs=dict(details.specs),
                )
        return None

    async def _fetch_product_record(
        self, session_id: str, product_id: str
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        """The UCP record for ``product_id`` plus the Store API document when it was needed.

        Live 6.7.13 quirk: ``GET /ucp/v1/catalog/product/{family}`` answers with the
        family's *first child* while ``catalog-lookup`` (and the MCP tool) answer with the
        family itself. When the answered id differs from the requested one the Store API
        decides which side is the parent, so a family never gets filed as a variant of
        its own child.
        """
        record = await self._ucp_product(
            session_id, "get_product", {"catalog": {"id": product_id, "context": _CONTEXT}}
        )
        if record is None or _record_id(record) == product_id:
            return record, None
        try:
            store = await self.store_api.product(product_id)
        except StoreApiError:
            store = None
        # The Store API resolves a family id to its best child too, but that child carries
        # ``parentId == <requested id>`` — which is how we know the request was the family.
        store_parent = store.get("parentId") if store else None
        if store is None or (store_parent and store_parent != product_id):
            return record, store  # requested a child; the shop answered with its family
        family = await self._ucp_product(
            session_id, "lookup_catalog", {"catalog": {"ids": [product_id], "context": _CONTEXT}}
        )
        if family is not None and _record_id(family) == product_id:
            return family, store
        fallback = _store_api_to_ucp(store)
        fallback["id"] = product_id  # the Store API answered the family's best child
        return fallback, store

    async def _ucp_product(
        self, session_id: str, method: str, params: dict[str, Any]
    ) -> dict[str, Any] | None:
        try:
            payload = await self._ucp(session_id, method, params)
        except UcpError as error:
            logger.info("UCP %s failed: %s", method, error)
            return None
        record = payload.get("product") or payload
        if isinstance(record, dict) and _record_id(record):
            return record
        found = payload.get("products") or []
        return found[0] if isinstance(found, list) and found else None

    async def _enrich_variants(
        self, state: _SessionState, details: ProductDetails, store: dict[str, Any] | None
    ) -> None:
        """Real children (and the family's delivery time) from the Store API."""
        try:
            store = store or await self.store_api.product(details.product_id)
        except StoreApiError:
            store = None
        if not store:
            return
        family_id = str(store.get("parentId") or store.get("id") or details.product_id)
        children = list(store.get("children") or [])
        if not children:
            try:
                children = await self.store_api.child_products(family_id)
            except StoreApiError:
                children = []
        delivery_name = _translated(store.get("deliveryTime") or {}, "name")
        if delivery_name:
            details.specs["deliveryTime"] = str(delivery_name)
        if not children:
            self._remember_details(state, details)
            return
        parent_doc = {"id": details.product_id, "name": details.title, "cover": store.get("cover")}
        variants = [_variant_from_store(parent_doc, child) for child in children]
        merged = {v.product_id: v for v in details.variants}
        merged.update({v.product_id: v for v in variants})
        details.variants = [v for v in merged.values() if v.product_id != details.product_id]
        details.options = _options_of(details.variants)
        details.in_stock = (
            any(v.in_stock for v in details.variants) if details.variants else details.in_stock
        )
        self._remember_details(state, details)

    def _remember_product(self, state: _SessionState, record: dict[str, Any]) -> ProductDetails:
        product_id = _record_id(record)
        price, currency = _product_price(record)
        description = _strip_html(record.get("description")) or _translated(record, "description")
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
            title=str(record.get("title") or _translated(record, "name") or product_id),
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
            specs=dict(existing.specs) if existing else {},
        )
        return self._remember_details(state, details)

    def _remember_details(self, state: _SessionState, details: ProductDetails) -> ProductDetails:
        state.currency = details.currency
        for variant in details.variants:
            if variant.product_id != details.product_id:
                self.variant_of[variant.product_id] = details.product_id
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
        self._remember_details(_SessionState(), details)

    def _map_variant(self, record: dict[str, Any], variant: dict[str, Any]) -> Product:
        price, currency = _money(
            variant.get("price") or {}, record.get("currency") or DEFAULT_CURRENCY
        )
        options = {
            str(opt.get("name") or "Option"): str(opt.get("label") or opt.get("value") or "")
            for opt in variant.get("options") or []
            if isinstance(opt, dict)
        }
        parent_id = _record_id(record)
        variant_id = _record_id(variant) or parent_id
        title = variant.get("title") or " / ".join(options.values()) or parent_id
        family_title = record.get("title") or _translated(record, "name") or parent_id
        return Product(
            product_id=variant_id,
            title=f"{family_title} — {title}",
            price=price,
            currency=currency,
            image_url=_image(variant) or _image(record),
            attributes=options,
            option_values=options,
            variant_of=parent_id,
            in_stock=_in_stock(variant),
        )

    # ------------------------------------------------------------------ cart

    async def get_cart(self, session: ShoppingSessionContext) -> Cart:
        state = self._state(session)
        if state.cart_id is None:
            return Cart(currency=state.currency)
        try:
            payload = await self._ucp(session.session_id, "get_cart", {"id": state.cart_id})
        except UcpCartGoneError:
            self._drop_cart(session.session_id, state)
            return Cart(currency=state.currency)
        return self._map_cart(state, payload)

    async def add_to_cart(
        self, session: ShoppingSessionContext, product_id: str, quantity: int
    ) -> Cart:
        state = self._state(session)
        variant_id = await self._resolve_variant(session, state, product_id)
        self._assert_available(variant_id)
        await self._refresh_lines(session, state)
        already = state.lines.get(variant_id)
        line_items = self._line_items(state, variant_id, (already[1] if already else 0) + quantity)
        if state.cart_id is None:
            return await self._create_cart(session, state, line_items)
        try:
            payload = await self._ucp(
                session.session_id,
                "update_cart",
                {"id": state.cart_id, "cart": {"line_items": line_items}},
            )
        except UcpCartGoneError:
            self._drop_cart(session.session_id, state)
            return await self._create_cart(
                session, state, [{"item": {"id": variant_id}, "quantity": quantity}]
            )
        return self._map_cart(state, payload)

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
        await self._refresh_lines(session, state)
        variant_id = (
            product_id
            if product_id in state.lines
            else state.default_variant.get(product_id)
            or self.default_variants.get(product_id, product_id)
        )
        if state.cart_id is None or variant_id not in state.lines:
            return await self.get_cart(session)
        try:
            payload = await self._ucp(
                session.session_id,
                "update_cart",
                {
                    "id": state.cart_id,
                    "cart": {"line_items": self._line_items(state, variant_id, quantity)},
                },
            )
        except UcpCartGoneError:
            self._drop_cart(session.session_id, state)
            return Cart(currency=state.currency)
        return self._map_cart(state, payload)

    async def _create_cart(
        self,
        session: ShoppingSessionContext,
        state: _SessionState,
        line_items: list[dict[str, Any]],
    ) -> Cart:
        payload = await self._ucp(
            session.session_id,
            "create_cart",
            {"cart": {"line_items": line_items, "context": _CONTEXT}},
        )
        self.handoff.revoke(session.session_id)
        return self._map_cart(state, payload)

    async def _refresh_lines(self, session: ShoppingSessionContext, state: _SessionState) -> None:
        if state.cart_id is None:
            return
        try:
            payload = await self._ucp(session.session_id, "get_cart", {"id": state.cart_id})
        except UcpCartGoneError:
            self._drop_cart(session.session_id, state)
            return
        self._map_cart(state, payload)

    @staticmethod
    def _line_items(state: _SessionState, variant_id: str, quantity: int) -> list[dict[str, Any]]:
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

    def _drop_cart(self, session_id: str, state: _SessionState) -> None:
        state.cart_id = None
        state.lines = {}
        self.handoff.revoke(session_id)

    async def _resolve_variant(
        self, session: ShoppingSessionContext, state: _SessionState, product_id: str
    ) -> str:
        if product_id in state.lines or product_id in self.variant_of:
            return product_id
        details = self.products.get(product_id)
        if details is None or (details.variants and product_id not in self.default_variants):
            await self.get_product_details(session, product_id)
        return (
            state.default_variant.get(product_id)
            or self.default_variants.get(product_id)
            or product_id
        )

    def _assert_available(self, variant_id: str) -> None:
        parent_id = self.variant_of.get(variant_id)
        if parent_id is not None:
            family = self.products.get(parent_id)
            variant = next(
                (v for v in (family.variants if family else []) if v.product_id == variant_id), None
            )
            if variant is not None and not variant.in_stock:
                siblings = [v.product_id for v in family.variants if v.in_stock]  # type: ignore[union-attr]
                raise Unavailable(
                    f"{variant_id} is unavailable"
                    + (f"; in stock: {', '.join(siblings)}" if siblings else "")
                )
            return
        details = self.products.get(variant_id)
        if details is not None and not details.variants and details.in_stock is False:
            raise Unavailable(f"{variant_id} is unavailable")

    def _map_cart(self, state: _SessionState, cart: dict[str, Any]) -> Cart:
        state.cart_id = str(cart.get("id") or state.cart_id)
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

    # ------------------------------------------------------------------ checkout & account

    async def checkout_handoff(
        self, session: ShoppingSessionContext, cart: Cart
    ) -> list[CheckoutHandoff]:
        url = self.checkout_url_for(session.session_id)
        if not url or not cart.items:
            return []
        return [CheckoutHandoff(url=url, label=HANDOFF_LABEL)]

    async def get_preferences(self, session: ShoppingSessionContext) -> UserPreferences:
        return UserPreferences(
            user_id=session.user_id,
            display_name="Guest",
            default_location="DE",
            preferences={"language": "de", "currency": DEFAULT_CURRENCY},
        )

    # ------------------------------------------------------------------ orders

    def _order_context_token(self, session_id: str) -> str | None:
        customer = (
            self._customer_token_provider(session_id) if self._customer_token_provider else None
        )
        return customer or self.cart_id_for(session_id)

    async def get_orders(self, session: ShoppingSessionContext, limit: int = 5) -> list[Order]:
        token = self._order_context_token(session.session_id)
        if not token:
            return []
        try:
            records = await self.store_api.orders(token, limit=max(limit, 1))
        except StoreApiError:
            return []
        return [_map_order(record) for record in records[:limit]]

    async def get_order(self, session: ShoppingSessionContext, order_id: str) -> Order | None:
        token = self._order_context_token(session.session_id)
        if not token:
            return None
        try:
            records = await self.store_api.orders(token)
        except StoreApiError:
            return None
        for record in records:
            if order_id in {str(record.get("id")), str(record.get("orderNumber"))}:
                return _map_order(record)
        return None

    # ------------------------------------------------------------------ policies & facts

    async def search_policies(self, session: ShoppingSessionContext, query: str) -> list[Policy]:
        return await self.policies.search(session, query)

    async def get_disclosure(
        self, session: ShoppingSessionContext, product_id: str
    ) -> Disclosure | None:
        try:
            product = await self.store_api.product(product_id)
            if not product and (parent := self.variant_of.get(product_id)):
                product = await self.store_api.product(parent)
        except StoreApiError:
            return None
        if not product:
            return None
        return disclosure_from_store_product(product_id, product)

    async def get_fulfillment_options(
        self, session: ShoppingSessionContext, product_ids: list[str]
    ) -> list[FulfillmentOption]:
        try:
            methods = await self.store_api.shipping_methods(self.cart_id_for(session.session_id))
        except StoreApiError:
            return []
        product_eta = self._product_eta(product_ids)
        options: list[FulfillmentOption] = []
        for method in methods:
            name = str(_translated(method, "name") or "Versand")
            fee = _shipping_fee(method)
            method_eta = _translated(method.get("deliveryTime") or {}, "name")
            eta = f"{name}: {method_eta or product_eta}"
            if method_eta and product_eta != DEFAULT_ETA:
                eta = f"{name}: {method_eta} (Verfügbarkeit: {product_eta})"
            options.append(FulfillmentOption(method="shipping", eta=eta, fee=fee))
        return options

    def _product_eta(self, product_ids: list[str]) -> str:
        for product_id in product_ids:
            details = self.products.get(product_id) or self.products.get(
                self.variant_of.get(product_id, "")
            )
            if details and details.specs.get("deliveryTime"):
                return str(details.specs["deliveryTime"])
        return DEFAULT_ETA


# ---------------------------------------------------------------------- document helpers


def _within_price(product: Product, filters: SearchFilters) -> bool:
    if filters.min_price is not None and product.price < filters.min_price:
        return False
    return not (filters.max_price is not None and product.price > filters.max_price)


def _product_price(record: dict[str, Any]) -> tuple[float, str]:
    currency = record.get("currency") or DEFAULT_CURRENCY
    if record.get("price_range"):
        price_range = record["price_range"]
        return _money(price_range.get("min") or price_range, currency)
    if record.get("calculatedPrice"):
        return round(float(record["calculatedPrice"].get("unitPrice") or 0), 2), DEFAULT_CURRENCY
    if "price" in record:
        return _money(record["price"], currency)
    return 0.0, currency


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
    if categories and isinstance(categories[0], dict):
        return _translated(categories[0], "name")
    return None


def _brand(record: dict[str, Any]) -> str | None:
    manufacturer = record.get("manufacturer") or {}
    if isinstance(manufacturer, dict):
        return _translated(manufacturer, "name")
    return None


def _options_of(variants: list[Product]) -> dict[str, list[str]]:
    options: dict[str, list[str]] = {}
    for variant in variants:
        for key, value in variant.option_values.items():
            options.setdefault(key, [])
            if value not in options[key]:
                options[key].append(value)
    return options


def _family_options(record: dict[str, Any], variants: list[Product]) -> dict[str, list[str]]:
    options: dict[str, list[str]] = {}
    for spec in record.get("options") or []:
        if isinstance(spec, dict) and spec.get("name"):
            values = [
                str(value.get("label") or value.get("name") or "")
                if isinstance(value, dict)
                else str(value)
                for value in spec.get("values") or []
            ]
            options[str(spec["name"])] = [v for v in values if v]
    return options or _options_of(variants)


def _store_api_to_ucp(product: dict[str, Any]) -> dict[str, Any]:
    name = _translated(product, "name")
    description = _translated(product, "description")
    price = (product.get("calculatedPrice") or {}).get("unitPrice")
    return {
        "id": product.get("id"),
        "title": name,
        "name": name,
        "description": {"html": description} if description else None,
        "price": price,
        "currency": DEFAULT_CURRENCY,
        "media": [
            {"type": "image", "url": ((product.get("cover") or {}).get("media") or {}).get("url")}
        ],
        "available": product.get("available", True),
        "categories": product.get("categories") or [],
        "manufacturer": product.get("manufacturer"),
        "variants": [
            {
                "id": child.get("id"),
                "title": _translated(child, "name"),
                "price": {
                    "amount": int(
                        round(
                            float((child.get("calculatedPrice") or {}).get("unitPrice") or 0) * 100
                        )
                    ),
                    "currency": DEFAULT_CURRENCY,
                },
                "availability": {"available": _in_stock(child)},
                "options": [
                    {
                        "name": _translated(opt.get("group") or {}, "name") or "Option",
                        "label": _translated(opt, "name"),
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
        group = _translated(opt.get("group") or {}, "name") or "Option"
        options[str(group)] = str(_translated(opt, "name") or "")
    title = _translated(child, "name") or " / ".join(options.values())
    parent_title = _translated(parent, "name") or ""
    return Product(
        product_id=str(child.get("id")),
        title=f"{parent_title} — {title}"
        if parent_title and not str(title).startswith(parent_title)
        else str(title),
        price=round(price, 2),
        currency=DEFAULT_CURRENCY,
        image_url=((child.get("cover") or parent.get("cover") or {}).get("media") or {}).get("url"),
        attributes=options,
        option_values=options,
        variant_of=str(parent.get("id")),
        in_stock=_in_stock(child),
    )


def _shipping_fee(method: dict[str, Any]) -> float:
    """The first price tier's gross amount in the shop currency; 0.0 when none is set."""
    tiers = sorted(
        (p for p in method.get("prices") or [] if isinstance(p, dict)),
        key=lambda p: float(p.get("quantityStart") or 0),
    )
    for tier in tiers:
        for row in tier.get("currencyPrice") or []:
            if isinstance(row, dict) and row.get("gross") is not None:
                try:
                    return round(float(row["gross"]), 2)
                except (TypeError, ValueError):
                    continue
    return 0.0


def _order_status(record: dict[str, Any]) -> OrderStatus:
    order_state = str(((record.get("stateMachineState") or {}).get("technicalName")) or "")
    if order_state in _ORDER_STATE:
        return _ORDER_STATE[order_state]
    for transaction in record.get("transactions") or []:
        state = str(((transaction.get("stateMachineState") or {}).get("technicalName")) or "")
        if state in _TRANSACTION_STATE:
            return _TRANSACTION_STATE[state]
    for delivery in record.get("deliveries") or []:
        state = str(((delivery.get("stateMachineState") or {}).get("technicalName")) or "")
        if state in _DELIVERY_STATE:
            return _DELIVERY_STATE[state]
    if order_state == "completed":
        return OrderStatus.DELIVERED
    return OrderStatus.PROCESSING


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            pass
    return datetime.now(UTC)


def _map_order(record: dict[str, Any]) -> Order:
    currency = ((record.get("currency") or {}).get("isoCode")) or DEFAULT_CURRENCY
    items: list[OrderItem] = []
    for line in record.get("lineItems") or []:
        if line.get("type") not in {None, "product"}:
            continue
        payload = line.get("payload") or {}
        options = {
            str(o.get("group") or "Option"): str(o.get("option") or "")
            for o in payload.get("options") or []
            if isinstance(o, dict)
        }
        items.append(
            OrderItem(
                product_id=str(
                    line.get("productId") or line.get("referencedId") or line.get("id") or ""
                ),
                title=str(line.get("label") or "item"),
                quantity=int(line.get("quantity") or 1),
                price=round(float(line.get("unitPrice") or 0), 2),
                option_values=options,
                variant_of=str(payload["parentId"]) if payload.get("parentId") else None,
            )
        )
    tracking_url: str | None = None
    estimated: str | None = None
    for delivery in record.get("deliveries") or []:
        codes = delivery.get("trackingCodes") or []
        template = (delivery.get("shippingMethod") or {}).get("trackingUrl")
        if codes and template and "%s" in str(template):
            tracking_url = str(template).replace("%s", str(codes[0]))
        latest = delivery.get("shippingDateLatest")
        if latest and not estimated:
            estimated = str(latest)[:10]
    return Order(
        order_id=str(record.get("orderNumber") or record.get("id")),
        status=_order_status(record),
        placed_at=_parse_datetime(record.get("orderDateTime")),
        items=items,
        total=round(float(record.get("amountTotal") or 0), 2),
        currency=str(currency),
        estimated_delivery=estimated,
        tracking_url=tracking_url,
    )
