# Copyright 2026 Shopware × Claude Commerce Agents authors.
# SPDX-License-Identifier: Apache-2.0

"""Replay of Shopware-shaped UCP + Store API responses over ``httpx.MockTransport``.

No test in this package touches the network. Catalog documents match the UCP REST
shapes Shopware's ``SwagAgenticCommerce`` mapper emits (hex UUIDs, cart id =
``sw-context-token``). Cart and checkout are stateful so the lifecycle tests can
create / patch / get without a combinatorial fixture dump.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

PRODUCT_ID = "11111111111111111111111111111111"
VARIANT_S = "22222222222222222222222222222222"
VARIANT_M = "33333333333333333333333333333333"
VARIANT_L = "44444444444444444444444444444444"
OIL_ID = "55555555555555555555555555555555"
CART_ID = "66666666666666666666666666666666"
GONE_CART_ID = "00000000000000000000000000000000"
CHECKOUT_ID = "77777777777777777777777777777777"
CONTINUE_URL = f"http://localhost:8080/checkout/confirm?checkoutId={CHECKOUT_ID}"
SEARCH_QUERY = "shirt"

_PRICE = {"amount": 2999, "currency": "EUR"}


def _variant(vid: str, size: str, available: bool) -> dict[str, Any]:
    return {
        "id": vid,
        "title": size,
        "price": dict(_PRICE),
        "availability": {"available": available},
        "options": [{"name": "Size", "label": size}],
        "image_url": "https://cdn.example/shirt.jpg",
    }


SHIRT: dict[str, Any] = {
    "id": PRODUCT_ID,
    "title": "Claude Commerce T-Shirt",
    "name": "Claude Commerce T-Shirt",
    "description": {"html": "Organic cotton T-shirt in three sizes."},
    "price": dict(_PRICE),
    "currency": "EUR",
    "image_url": "https://cdn.example/shirt.jpg",
    "availability": {"available": True},
    "tags": ["Apparel"],
    "variants": [
        _variant(VARIANT_S, "S", True),
        _variant(VARIANT_M, "M", True),
        _variant(VARIANT_L, "L", False),
    ],
}

OIL: dict[str, Any] = {
    "id": OIL_ID,
    "title": "Extra Virgin Olive Oil 500 ml",
    "name": "Extra Virgin Olive Oil 500 ml",
    "description": {"html": "Cold-pressed olive oil. Grundpreis is shown on the product."},
    "price": {"amount": 1290, "currency": "EUR"},
    "currency": "EUR",
    "image_url": "https://cdn.example/oil.jpg",
    "availability": {"available": True},
    "tags": ["Grocery"],
    "variants": [],
}

CATALOG = {PRODUCT_ID: SHIRT, OIL_ID: OIL, VARIANT_S: SHIRT, VARIANT_M: SHIRT, VARIANT_L: SHIRT}


def _store_child(vid: str, size: str, stock: int) -> dict[str, Any]:
    return {
        "id": vid,
        "name": f"Claude Commerce T-Shirt — {size}",
        "translated": {"name": f"Claude Commerce T-Shirt — {size}"},
        "available": stock > 0,
        "availableStock": stock,
        "stock": stock,
        "calculatedPrice": {"unitPrice": 29.99},
        "options": [{"name": size, "translated": {"name": size}, "group": {"name": "Size", "translated": {"name": "Size"}}}],
        "cover": {"media": {"url": "https://cdn.example/shirt.jpg"}},
    }


STORE_PRODUCTS: dict[str, dict[str, Any]] = {
    PRODUCT_ID: {
        "id": PRODUCT_ID,
        "name": "Claude Commerce T-Shirt",
        "translated": {"name": "Claude Commerce T-Shirt", "description": "Organic cotton T-shirt."},
        "available": True,
        "availableStock": 32,
        "calculatedPrice": {"unitPrice": 29.99},
        "cover": {"media": {"url": "https://cdn.example/shirt.jpg"}},
        "deliveryTime": {"name": "1–3 Werktage", "translated": {"name": "1–3 Werktage"}, "min": 1, "max": 3},
        "children": [
            _store_child(VARIANT_S, "S", 20),
            _store_child(VARIANT_M, "M", 12),
            _store_child(VARIANT_L, "L", 0),
        ],
        "manufacturer": {"name": "Commerce Agents", "translated": {"name": "Commerce Agents"}},
        "categories": [{"name": "Apparel", "translated": {"name": "Apparel"}}],
    },
    OIL_ID: {
        "id": OIL_ID,
        "name": "Extra Virgin Olive Oil 500 ml",
        "translated": {"name": "Extra Virgin Olive Oil 500 ml", "description": "Cold-pressed."},
        "available": True,
        "availableStock": 40,
        "calculatedPrice": {
            "unitPrice": 12.90,
            "referencePrice": {"price": 25.80, "unitName": "1 l"},
        },
        "purchaseUnit": 0.5,
        "referenceUnit": 1.0,
        "cover": {"media": {"url": "https://cdn.example/oil.jpg"}},
        "deliveryTime": {"name": "2–4 Werktage", "translated": {"name": "2–4 Werktage"}, "min": 2, "max": 4},
        "children": [],
        "unit": {"shortCode": "l", "name": "Liter"},
    },
}


class ShopwareReplay:
    """In-memory Shopware UCP + Store API for tests."""

    def __init__(self) -> None:
        self.carts: dict[str, dict[str, Any]] = {}
        self.checkouts: dict[str, dict[str, Any]] = {}
        self._cart_seq = 0

    def handle(self, request: httpx.Request) -> httpx.Response:
        parsed = urlparse(str(request.url))
        path = parsed.path
        method = request.method.upper()
        body = _json_body(request)

        if method == "GET" and path.endswith("/.well-known/ucp"):
            return httpx.Response(200, json=_discovery())

        if path.startswith("/ucp/v1/"):
            return self._ucp_rest(method, path[len("/ucp/v1") :], body)

        if path == "/ucp/mcp" and method == "POST":
            return self._ucp_mcp(body)

        if path == "/store-api/context":
            return httpx.Response(
                200,
                json={"salesChannel": {"name": "Storefront", "translated": {"name": "Storefront"}}},
            )
        if path == "/store-api/product" and method == "POST":
            parent = None
            for item in body.get("filter") or []:
                if isinstance(item, dict) and item.get("field") == "parentId":
                    parent = item.get("value")
            children = STORE_PRODUCTS.get(parent, {}).get("children") or []
            return httpx.Response(200, json={"elements": deepcopy(children)})
        if path.startswith("/store-api/product/"):
            pid = path.rsplit("/", 1)[-1]
            product = STORE_PRODUCTS.get(pid)
            if product is None:
                return httpx.Response(404, json={"errors": [{"detail": "not found"}]})
            return httpx.Response(200, json={"product": deepcopy(product)})
        if path == "/store-api/search":
            query = (parsed.query or "") + json.dumps(body)
            products = [deepcopy(SHIRT)] if "shirt" in query.lower() or "t-shirt" in query.lower() else [deepcopy(SHIRT), deepcopy(OIL)]
            return httpx.Response(200, json={"elements": products})
        if path == "/store-api/shipping-method":
            return httpx.Response(
                200,
                json={
                    "elements": [
                        {
                            "name": "Standard",
                            "translated": {"name": "Standard"},
                            "prices": [{"currencyPrice": [{"gross": 4.95}]}],
                        }
                    ]
                },
            )
        if path.startswith("/store-api/navigation/"):
            return httpx.Response(200, json=[])
        if path.startswith("/store-api/category/"):
            return httpx.Response(200, json={})

        return httpx.Response(404, json={"detail": f"unmocked {method} {path}"})

    def _ucp_rest(self, method: str, path: str, body: dict[str, Any]) -> httpx.Response:
        if method == "POST" and path == "/catalog/search":
            query = str(body.get("query") or "").lower()
            products = []
            if not query or query in {"*", "a"} or "shirt" in query or "t-shirt" in query or "claude" in query:
                products.append(deepcopy(SHIRT))
            if "oil" in query or "olive" in query or query in {"", "*", "a"}:
                products.append(deepcopy(OIL))
            if query and "zzzz" in query:
                products = []
            return httpx.Response(200, json={"products": products})

        if method == "GET" and path.startswith("/catalog/product/"):
            pid = path.rsplit("/", 1)[-1]
            record = CATALOG.get(pid)
            if record is None:
                return httpx.Response(
                    404,
                    json={"messages": [{"type": "error", "content": "Product not found"}]},
                )
            return httpx.Response(200, json={"product": deepcopy(record)})

        if method == "POST" and path == "/catalog/lookup":
            ids = body.get("ids") or []
            found = [deepcopy(CATALOG[i]) for i in ids if i in CATALOG]
            return httpx.Response(200, json={"products": found})

        if method == "POST" and path == "/carts":
            return httpx.Response(201, json=self._create_cart(body.get("line_items") or []))

        if path.startswith("/carts/"):
            rest = path[len("/carts/") :]
            if rest.endswith("/cancel"):
                cart_id = rest[: -len("/cancel")]
                self.carts.pop(cart_id, None)
                return httpx.Response(200, json={"id": cart_id, "line_items": []})
            cart_id = rest
            if cart_id == GONE_CART_ID or cart_id not in self.carts:
                return httpx.Response(
                    404,
                    json={
                        "messages": [
                            {
                                "type": "error",
                                "code": "cart_not_found",
                                "content": "The requested cart is gone",
                            }
                        ]
                    },
                )
            if method == "GET":
                return httpx.Response(200, json=deepcopy(self.carts[cart_id]))
            if method == "PATCH":
                lines = body.get("line_items") or []
                self.carts[cart_id] = self._cart_document(cart_id, lines)
                return httpx.Response(200, json=deepcopy(self.carts[cart_id]))

        if method == "POST" and path == "/checkout-sessions":
            document = {
                "id": CHECKOUT_ID,
                "continue_url": CONTINUE_URL,
                "links": [{"rel": "continue", "href": CONTINUE_URL}],
                "line_items": body.get("line_items") or [],
                "cart_id": body.get("cart_id"),
            }
            self.checkouts[CHECKOUT_ID] = document
            return httpx.Response(201, json=document)

        if path.startswith("/checkout-sessions/"):
            cid = path.split("/")[2]
            if cid not in self.checkouts:
                return httpx.Response(
                    404, json={"messages": [{"type": "error", "content": "checkout not found"}]}
                )
            if method == "PATCH":
                self.checkouts[cid] = {**self.checkouts[cid], **body, "id": cid}
            return httpx.Response(200, json=deepcopy(self.checkouts[cid]))

        if method == "POST" and path.endswith("/complete"):
            return httpx.Response(400, json={"detail": "complete_checkout is disabled in tests"})

        return httpx.Response(404, json={"detail": f"unmocked UCP {method} {path}"})

    def _ucp_mcp(self, body: dict[str, Any]) -> httpx.Response:
        params = body.get("params") or {}
        name = params.get("name") or ""
        arguments = params.get("arguments") or {}
        mapping = {
            "shopware-ucp-catalog-search": ("search_catalog", "POST", "/catalog/search"),
            "shopware-ucp-catalog-lookup": ("lookup_catalog", "POST", "/catalog/lookup"),
            "shopware-ucp-cart-create": ("create_cart", "POST", "/carts"),
            "shopware-ucp-cart-get": ("get_cart", "GET", f"/carts/{arguments.get('id')}"),
            "shopware-ucp-cart-update": ("update_cart", "PATCH", f"/carts/{arguments.get('id')}"),
        }
        if name not in mapping:
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": body.get("id"),
                    "error": {"code": -32601, "message": f"Unknown tool {name}"},
                },
            )
        _op, method, path = mapping[name]
        payload = arguments
        if "payload" in arguments:
            try:
                payload = json.loads(arguments["payload"])
            except (TypeError, ValueError):
                payload = arguments
        rest = self._ucp_rest(method, path, payload)
        try:
            data = rest.json()
        except ValueError:
            data = {"detail": rest.text}
        if rest.status_code >= 400:
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": body.get("id"),
                    "result": {
                        "isError": True,
                        "content": [{"type": "text", "text": json.dumps(data)}],
                    },
                },
            )
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": body.get("id"),
                "result": {"structuredContent": data},
            },
        )

    def _create_cart(self, line_items: list[dict[str, Any]]) -> dict[str, Any]:
        self._cart_seq += 1
        cart_id = CART_ID if self._cart_seq == 1 else f"{CART_ID[:-1]}{self._cart_seq}"
        document = self._cart_document(cart_id, line_items)
        self.carts[cart_id] = document
        return deepcopy(document)

    def _cart_document(self, cart_id: str, line_items: list[dict[str, Any]]) -> dict[str, Any]:
        mapped = []
        for index, line in enumerate(line_items, start=1):
            if int(line.get("quantity") or 0) <= 0:
                continue
            item = line.get("item") or {}
            vid = str(item.get("id") or "")
            title = "Claude Commerce T-Shirt — S"
            for variant in SHIRT["variants"]:
                if variant["id"] == vid:
                    title = f"Claude Commerce T-Shirt — {variant['title']}"
            if vid == OIL_ID:
                title = OIL["title"]
            mapped.append(
                {
                    "id": str(line.get("id") or f"line-{index}"),
                    "quantity": int(line.get("quantity") or 1),
                    "item": {
                        "id": vid,
                        "title": title,
                        "price": dict(_PRICE if vid != OIL_ID else OIL["price"]),
                    },
                }
            )
        return {
            "id": cart_id,
            "currency": "EUR",
            "continue_url": CONTINUE_URL,
            "links": [{"rel": "continue", "href": CONTINUE_URL}],
            "line_items": mapped,
        }


def _json_body(request: httpx.Request) -> dict[str, Any]:
    if not request.content:
        return {}
    try:
        data = json.loads(request.content)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _discovery() -> dict[str, Any]:
    path = DATA_DIR / "discovery.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "ucp": {"version": "2026-04-08"},
        "payment": {"handlers": []},
        "capabilities": {
            "dev.ucp.shopping.catalog": {"open": {"version": "2026-04-08"}},
            "dev.ucp.shopping.cart": {"open": {"version": "2026-04-08"}},
            "dev.ucp.shopping.checkout": {"open": {"version": "2026-04-08"}},
        },
        "services": {
            "dev.ucp.shopping": {
                "version": "2026-04-08",
                "rest": {"endpoint": "/ucp/v1"},
                "mcp": {"endpoint": "/ucp/mcp"},
            }
        },
    }


def replay_transport() -> httpx.MockTransport:
    shop = ShopwareReplay()
    return httpx.MockTransport(shop.handle)
