# Copyright 2026 Shopware × Claude Commerce Agents authors.
# SPDX-License-Identifier: Apache-2.0

"""Keyword policy index: Store API footer/service navigation + /agents.md + /llms.txt."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from shopping_agent import Policy, ShoppingSessionContext

if TYPE_CHECKING:
    from .store_api import StoreApiClient

_TAG = re.compile(r"<[^>]+>")
_FALLBACK = [
    Policy(
        policy_id="returns",
        title="Widerruf und Rückgabe",
        category="returns",
        content=(
            "Verbraucher haben ein gesetzliches Widerrufsrecht von 14 Tagen. "
            "Die Widerrufsfrist beginnt, sobald die Ware beim Kunden eingegangen ist. "
            "Details stehen in der Widerrufsbelehrung im Shop-Footer."
        ),
    ),
    Policy(
        policy_id="shipping",
        title="Versand und Lieferzeit",
        category="shipping",
        content=(
            "Lieferzeiten stehen am Produkt (deliveryTime). Versandkosten werden im "
            "Shopware-Checkout berechnet. Lieferungen nach Österreich nutzen die "
            "gleichen Versandarten, sofern die Versandart das Land abdeckt."
        ),
    ),
    Policy(
        policy_id="vat",
        title="Preise und MwSt.",
        category="pricing",
        content="Alle Storefront-Preise sind Bruttopreise inklusive gesetzlicher MwSt., sofern nicht anders gekennzeichnet.",
    ),
]


def _strip(html: str) -> str:
    return re.sub(r"\s+", " ", _TAG.sub(" ", html)).strip()


class PolicyIndex:
    def __init__(self, store_api: StoreApiClient) -> None:
        self._store_api = store_api
        self._policies: list[Policy] | None = None

    async def rebuild(self) -> list[Policy]:
        policies: list[Policy] = []
        for name in ("footer-navigation", "service-navigation"):
            tree = await self._store_api.navigation(name)
            await self._walk(tree, policies)
        for path, title in (("/agents.md", "agents.md"), ("/llms.txt", "llms.txt")):
            text = await self._store_api.text_file(path)
            if text.strip():
                policies.append(
                    Policy(policy_id=path.strip("/").replace(".", "-"), title=title, content=text[:4000])
                )
        self._policies = policies or list(_FALLBACK)
        return self._policies

    async def _walk(self, nodes: list[dict], policies: list[Policy]) -> None:
        for node in nodes:
            category_id = node.get("id") or node.get("categoryId")
            name = node.get("name") or node.get("translated", {}).get("name") or "Policy"
            if category_id:
                record = await self._store_api.category(str(category_id))
                cms = record.get("cmsPage") or record.get("slotConfig") or {}
                text = _extract_cms_text(cms) or _strip(str(record.get("description") or ""))
                if text:
                    policies.append(
                        Policy(policy_id=str(category_id), title=str(name), content=text[:4000])
                    )
            children = node.get("children") or node.get("elements") or []
            if children:
                await self._walk(children, policies)

    async def search(self, session: ShoppingSessionContext, query: str) -> list[Policy]:
        if self._policies is None:
            await self.rebuild()
        assert self._policies is not None
        tokens = {t.lower() for t in re.findall(r"[a-zA-ZäöüÄÖÜß]{3,}", query)}
        if not tokens:
            return self._policies[:5]
        scored: list[tuple[int, Policy]] = []
        for policy in self._policies:
            hay = f"{policy.title} {policy.content}".lower()
            score = sum(1 for token in tokens if token in hay)
            if score:
                scored.append((score, policy))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [policy for _, policy in scored[:8]] or self._policies[:3]


def _extract_cms_text(cms: dict) -> str:
    chunks: list[str] = []

    def walk(value: object) -> None:
        if isinstance(value, dict):
            for key in ("plain", "content", "value", "html"):
                if key in value and isinstance(value[key], str):
                    chunks.append(_strip(value[key]))
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(cms)
    return " ".join(chunk for chunk in chunks if chunk)
