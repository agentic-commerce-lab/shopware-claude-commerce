#!/usr/bin/env python3
"""Seed a small extra catalog: size variants (one OOS) and a Grundpreis product.

Uses the Shopware Admin API (password grant against the Administration client).
Idempotent: product numbers are stable (CA-TSHIRT / CA-OIL).
"""

from __future__ import annotations

import argparse
import json
import ssl
import sys
import urllib.error
import urllib.request
import uuid

CURRENCY_EUR = "b7d2554b0ce847cd82f3ac9bd1c0dfca"


def _uuid() -> str:
    return uuid.uuid4().hex


def _request(shop_url: str, method: str, path: str, payload=None, token: str | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode()
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        f"{shop_url}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=40, context=ssl.create_default_context()) as response:
            body = response.read()
            if not body:
                return {}
            return json.loads(body)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(f"{method} {path} -> {error.code}: {detail}") from error


def admin_token(client, shop_url: str, user: str, password: str) -> str:
    payload = _request(
        shop_url,
        "POST",
        "/api/oauth/token",
        {
            "grant_type": "password",
            "client_id": "administration",
            "username": user,
            "password": password,
        },
    )
    return payload["access_token"]


def api(client, shop_url: str, token: str, method: str, path: str, json=None):
    return _request(shop_url, method, path, json, token=token)


def search_id(client, shop_url, token, entity, field, value) -> str | None:
    body = api(
        client,
        shop_url,
        token,
        "POST",
        f"/api/search/{entity}",
        {
            "limit": 1,
            "filter": [{"type": "equals", "field": field, "value": value}],
        },
    )
    data = body.get("data") or []
    return data[0]["id"] if data else None


def first_id(client, shop_url, token, entity) -> str:
    body = api(client, shop_url, token, "POST", f"/api/search/{entity}", {"limit": 1})
    data = body.get("data") or []
    if not data:
        raise RuntimeError(f"No {entity} found")
    return data[0]["id"]


def tax_id(client, shop_url, token) -> str:
    body = api(
        client,
        shop_url,
        token,
        "POST",
        "/api/search/tax",
        {"limit": 5, "sort": [{"field": "taxRate", "order": "DESC"}]},
    )
    return body["data"][0]["id"]


def sales_channel_id(client, shop_url, token) -> str:
    body = api(
        client,
        shop_url,
        token,
        "POST",
        "/api/search/sales-channel",
        {
            "limit": 5,
            "filter": [
                {
                    "type": "equals",
                    "field": "typeId",
                    "value": "8a243080f92e4c719546314b577cf82b",
                }
            ],
        },
    )
    if not body.get("data"):
        return first_id(client, shop_url, token, "sales-channel")
    return body["data"][0]["id"]


def category_id(client, shop_url, token, sales_channel: str) -> str:
    channel = api(client, shop_url, token, "GET", f"/api/sales-channel/{sales_channel}")
    nav = (channel.get("data") or channel).get("navigationCategoryId")
    if nav:
        return nav
    return first_id(client, shop_url, token, "category")


def ensure_property_group(client, shop_url, token, name: str, options: list[str]) -> dict[str, str]:
    group_id = search_id(client, shop_url, token, "property-group", "name", name)
    if group_id is None:
        group_id = _uuid()
        api(
            client,
            shop_url,
            token,
            "POST",
            "/api/property-group",
            {
                "id": group_id,
                "name": name,
                "displayType": "text",
                "sortingType": "alphanumeric",
                "options": [{"id": _uuid(), "name": option} for option in options],
            },
        )
    body = api(
        client,
        shop_url,
        token,
        "POST",
        "/api/search/property-group-option",
        {
            "limit": 50,
            "filter": [{"type": "equals", "field": "groupId", "value": group_id}],
        },
    )
    mapping: dict[str, str] = {}
    for option in body.get("data") or []:
        attrs = option.get("attributes") or option
        mapping[attrs.get("name") or ""] = option["id"]
    for option in options:
        if option not in mapping:
            option_id = _uuid()
            api(
                client,
                shop_url,
                token,
                "POST",
                "/api/property-group-option",
                {"id": option_id, "groupId": group_id, "name": option},
            )
            mapping[option] = option_id
    return mapping


def unit_id(client, shop_url, token, short_code: str = "l") -> str | None:
    body = api(
        client,
        shop_url,
        token,
        "POST",
        "/api/search/unit",
        {
            "limit": 20,
            "filter": [{"type": "equals", "field": "shortCode", "value": short_code}],
        },
    )
    data = body.get("data") or []
    if data:
        return data[0]["id"]
    uid = _uuid()
    try:
        api(
            client,
            shop_url,
            token,
            "POST",
            "/api/unit",
            {"id": uid, "name": "Liter", "shortCode": short_code},
        )
        return uid
    except RuntimeError:
        return None


def upsert_product(client, shop_url, token, payload: dict) -> None:
    existing = search_id(client, shop_url, token, "product", "productNumber", payload["productNumber"])
    if existing:
        print(f"  already present: {payload['productNumber']}")
        return
    api(client, shop_url, token, "POST", "/api/product", payload)
    print(f"  created: {payload['productNumber']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shop-url", required=True)
    parser.add_argument("--user", default="admin")
    parser.add_argument("--password", default="shopware")
    args = parser.parse_args()
    shop_url = args.shop_url.rstrip("/")
    client = None

    try:
        token = admin_token(client, shop_url, args.user, args.password)
        tax = tax_id(client, shop_url, token)
        channel = sales_channel_id(client, shop_url, token)
        category = category_id(client, shop_url, token, channel)
        sizes = ensure_property_group(client, shop_url, token, "Size", ["S", "M", "L"])
        litre = unit_id(client, shop_url, token)

        parent_id = _uuid()
        vis = [{"salesChannelId": channel, "visibility": 30}]
        cats = [{"id": category}]
        price = [{"currencyId": CURRENCY_EUR, "gross": 29.99, "net": 25.20, "linked": True}]

        upsert_product(
            client,
            shop_url,
            token,
            {
                "id": parent_id,
                "productNumber": "CA-TSHIRT",
                "name": "Claude Commerce T-Shirt",
                "description": "Organic cotton T-shirt in three sizes. Size L is currently sold out.",
                "stock": 0,
                "taxId": tax,
                "price": price,
                "active": True,
                "visibilities": vis,
                "categories": cats,
                "configuratorSettings": [
                    {"optionId": sizes["S"]},
                    {"optionId": sizes["M"]},
                    {"optionId": sizes["L"]},
                ],
            },
        )
        for size, stock, number, pid in (
            ("S", 20, "CA-TSHIRT-S", _uuid()),
            ("M", 12, "CA-TSHIRT-M", _uuid()),
            ("L", 0, "CA-TSHIRT-L", _uuid()),
        ):
            upsert_product(
                client,
                shop_url,
                token,
                {
                    "id": pid,
                    "parentId": search_id(client, shop_url, token, "product", "productNumber", "CA-TSHIRT")
                    or parent_id,
                    "productNumber": number,
                    "name": f"Claude Commerce T-Shirt — {size}",
                    "stock": stock,
                    "isCloseout": size == "L",
                    "taxId": tax,
                    "price": price,
                    "active": True,
                    "options": [{"id": sizes[size]}],
                },
            )

        oil = {
            "id": _uuid(),
            "productNumber": "CA-OIL",
            "name": "Extra Virgin Olive Oil 500 ml",
            "description": "Cold-pressed olive oil. Grundpreis is shown on the product (PAngV).",
            "stock": 40,
            "taxId": tax,
            "price": [{"currencyId": CURRENCY_EUR, "gross": 12.90, "net": 10.84, "linked": True}],
            "active": True,
            "visibilities": vis,
            "categories": cats,
            "purchaseUnit": 0.5,
            "referenceUnit": 1.0,
            "packUnit": "bottle",
        }
        if litre:
            oil["unitId"] = litre
        upsert_product(client, shop_url, token, oil)
    except Exception as error:
        print(f"Seed skipped/failed: {error}", file=sys.stderr)
        return 0
    print("Catalog seed done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
