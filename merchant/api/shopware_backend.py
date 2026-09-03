# Copyright 2026 Shopware × Claude Commerce Agents authors.
# SPDX-License-Identifier: Apache-2.0

"""``MerchantBackend`` over Shopware Admin REST. Staging writes the ledger only;
``apply_change`` is the sole live write (via ``ShopwareWriter``)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from demo_common.merchant_fixtures import filter_listings
from merchant_agent import (
    ActorKind,
    AlertCounts,
    BusinessSnapshot,
    Campaign,
    CampaignDraft,
    ChangeItem,
    ChangeKind,
    ChangeLedger,
    InventoryActionItem,
    InventoryAlert,
    Listing,
    ListingDetails,
    ListingFilters,
    MerchantAgentConfig,
    MerchantBackend,
    MerchantSessionContext,
    MetricPoint,
    MetricSeries,
    OrderIssue,
    PriceUpdateItem,
    PricingContext,
    PromotionDraft,
    StagedChange,
)
from merchant_agent.changes import ChangeNotApplicable, GuardrailViolation, check_guardrails

from .admin_client import AdminTransport
from .agent_config import ShopwareSettings
from .catalog import CatalogCache, ProductRecord
from .staging import LISTING_FIELDS, ShopwareWriter, WriteFailed


class ShopwareMerchantBackend(MerchantBackend):
    def __init__(
        self,
        admin: AdminTransport,
        settings: ShopwareSettings,
        config: MerchantAgentConfig,
    ) -> None:
        self.admin = admin
        self._settings = settings
        self._config = config
        self.ledger = ChangeLedger(config)
        self.catalog = CatalogCache(admin)
        self._writer = ShopwareWriter(admin, self.catalog)
        self._orders: list[dict[str, Any]] = []

    @property
    def store_name(self) -> str:
        return self._settings.store_name or "Shopware"

    @property
    def display_currency(self) -> str:
        return "EUR"

    def all_listings(self) -> list[Listing]:
        return self.catalog.all_listings()

    async def warm(self) -> None:
        await self.catalog.refresh()
        try:
            payload = await self.admin.search(
                "order",
                {
                    "limit": 50,
                    "sort": [{"field": "orderDateTime", "order": "DESC"}],
                    "includes": {"order": ["id", "orderNumber", "amountTotal", "orderDateTime", "stateId"]},
                },
            )
            self._orders = payload.get("data") or []
        except Exception:
            self._orders = []

    async def get_business_snapshot(
        self, session: MerchantSessionContext, period: str | None = None
    ) -> BusinessSnapshot:
        await self._ensure_catalog()
        sales = 0.0
        for row in self._orders:
            attrs = row.get("attributes") or row
            try:
                sales += float(attrs.get("amountTotal") or 0)
            except (TypeError, ValueError):
                pass
        alerts = await self.get_inventory_alerts(session)
        issues = await self.get_order_issues(session)
        return BusinessSnapshot(
            period=period or "last_30d",
            sales=round(sales, 2),
            orders=len(self._orders),
            average_order_value=round(sales / len(self._orders), 2) if self._orders else None,
            currency="EUR",
            alerts=AlertCounts(
                low_stock=sum(1 for a in alerts if a.kind == "low_stock"),
                slow_movers=sum(1 for a in alerts if a.kind == "slow_mover"),
                order_issues=len(issues),
                pending_changes=len(self.ledger.pending()),
            ),
            note="Order totals from Admin API search (last 50). Traffic is not available.",
        )

    async def query_metrics(
        self,
        session: MerchantSessionContext,
        metric: str,
        period: str | None = None,
        granularity: str = "day",
        segment: str | None = None,
    ) -> MetricSeries:
        if metric not in {"sales", "orders"}:
            return MetricSeries(
                metric=metric,
                points=[],
                note=f"{metric} is not sourced from Shopware Admin in this deployment",
            )
        points: list[MetricPoint] = []
        today = datetime.now(UTC).date()
        by_day: dict[str, float] = {}
        for row in self._orders:
            attrs = row.get("attributes") or row
            stamp = str(attrs.get("orderDateTime") or "")[:10]
            if not stamp:
                continue
            value = float(attrs.get("amountTotal") or 0) if metric == "sales" else 1.0
            by_day[stamp] = by_day.get(stamp, 0.0) + value
        for offset in range(6, -1, -1):
            day = (today - timedelta(days=offset)).isoformat()
            points.append(MetricPoint(date=day, value=round(by_day.get(day, 0.0), 2)))
        return MetricSeries(metric=metric, unit="EUR" if metric == "sales" else "count", points=points)

    async def get_campaign_performance(
        self, session: MerchantSessionContext, campaign_id: str | None = None
    ) -> list[Campaign]:
        raise ChangeNotApplicable(
            "campaign performance is not available — Shopware has no marketing-activity "
            "read in this deployment"
        )

    async def search_listings(
        self,
        session: MerchantSessionContext,
        query: str,
        filters: ListingFilters | None = None,
        limit: int = 8,
    ) -> list[Listing]:
        await self._ensure_catalog()
        listings = self.catalog.all_listings()
        tokens = {t.lower() for t in query.split() if len(t) > 1}
        if tokens and query.strip() not in {"", "*", "all"}:
            listings = [
                listing
                for listing in listings
                if any(token in f"{listing.title} {listing.listing_id}".lower() for token in tokens)
            ]
        return filter_listings(listings, filters, limit, sales_of=lambda _id: 0.0)

    async def get_listing(
        self, session: MerchantSessionContext, listing_id: str
    ) -> ListingDetails | None:
        record = await self.catalog.get(listing_id)
        return None if record is None else record.to_details()

    async def get_inventory_alerts(self, session: MerchantSessionContext) -> list[InventoryAlert]:
        await self._ensure_catalog()
        threshold = self._settings.low_stock_default
        alerts: list[InventoryAlert] = []
        for record in self._iter_stock_rows():
            if record.stock <= threshold:
                alerts.append(
                    InventoryAlert(
                        listing_id=record.listing_id,
                        title=record.title,
                        kind="low_stock",
                        stock=record.stock,
                        threshold=threshold,
                        variant_of=record.parent_id,
                        storefront_visible=record.active,
                    )
                )
        return alerts

    async def get_order_issues(self, session: MerchantSessionContext) -> list[OrderIssue]:
        return []

    async def get_pricing_context(
        self, session: MerchantSessionContext, listing_id: str
    ) -> PricingContext | None:
        record = await self.catalog.get(listing_id)
        if record is None:
            return None
        variants = [
            PricingContext(
                listing_id=child.listing_id,
                current_price=child.price,
                currency="EUR",
                max_price_delta_pct=self._config.max_price_delta_pct,
                max_promotion_discount_pct=self._config.max_promotion_discount_pct,
            )
            for child in record.children
        ]
        return PricingContext(
            listing_id=record.listing_id,
            current_price=record.price,
            currency="EUR",
            margin_pct=None,
            max_price_delta_pct=self._config.max_price_delta_pct,
            max_promotion_discount_pct=self._config.max_promotion_discount_pct,
            variants=variants,
        )

    async def stage_listing_update(
        self,
        session: MerchantSessionContext,
        listing_id: str,
        fields: dict[str, Any],
        note: str | None = None,
    ) -> StagedChange:
        record = await self._require_record(listing_id)
        items: list[ChangeItem] = []
        for field, after in fields.items():
            if field not in LISTING_FIELDS:
                raise ChangeNotApplicable(
                    f"field {field!r} cannot be staged as a listing update on Shopware"
                )
            before = record.title if field in {"title", "name"} else record.description
            items.append(ChangeItem(target=listing_id, field=field, before=before, after=after))
        return self.ledger.stage(
            kind=ChangeKind.LISTING_UPDATE,
            summary=note or f"Update listing {record.title}",
            items=items,
            actor=session.operator,
            actor_kind=ActorKind.AGENT,
            currency="EUR",
        )

    async def stage_price_update(
        self,
        session: MerchantSessionContext,
        items: list[PriceUpdateItem],
        note: str | None = None,
    ) -> StagedChange:
        change_items: list[ChangeItem] = []
        notes: list[str] = []
        for item in items:
            record = await self._require_record(item.listing_id)
            change_items.append(
                ChangeItem(
                    target=item.listing_id,
                    field="price",
                    before=record.price,
                    after=item.new_price,
                )
            )
            if record.price:
                notes.append(f"{record.title}: {record.price} → {item.new_price} EUR")
        return self.ledger.stage(
            kind=ChangeKind.PRICE_UPDATE,
            summary=note or "Price update",
            items=change_items,
            actor=session.operator,
            actor_kind=ActorKind.AGENT,
            currency="EUR",
            guardrail_notes=notes,
        )

    async def stage_inventory_action(
        self,
        session: MerchantSessionContext,
        items: list[InventoryActionItem],
        note: str | None = None,
    ) -> StagedChange:
        change_items: list[ChangeItem] = []
        for item in items:
            record = await self._require_record(item.listing_id)
            if item.action == "restock":
                added = int(item.quantity or 0)
                change_items.append(
                    ChangeItem(
                        target=item.listing_id,
                        field="stock",
                        before=record.stock,
                        after=record.stock + added,
                    )
                )
            elif item.action == "pause":
                change_items.append(
                    ChangeItem(target=item.listing_id, field="status", before=record.status, after="paused")
                )
            else:
                change_items.append(
                    ChangeItem(target=item.listing_id, field="status", before=record.status, after="active")
                )
        return self.ledger.stage(
            kind=ChangeKind.INVENTORY_ACTION,
            summary=note or "Inventory action",
            items=change_items,
            actor=session.operator,
            actor_kind=ActorKind.AGENT,
            currency="EUR",
        )

    async def stage_promotion(
        self, session: MerchantSessionContext, promotion: PromotionDraft
    ) -> StagedChange:
        items = []
        for listing_id in promotion.listing_ids:
            record = await self._require_record(listing_id)
            after = round(record.price * (1 - promotion.discount_pct / 100), 2)
            items.append(
                ChangeItem(target=listing_id, field="price", before=record.price, after=after)
            )
        return self.ledger.stage(
            kind=ChangeKind.PROMOTION,
            summary=promotion.name,
            items=items,
            actor=session.operator,
            actor_kind=ActorKind.AGENT,
            currency="EUR",
        )

    async def stage_campaign(
        self, session: MerchantSessionContext, campaign: CampaignDraft
    ) -> StagedChange:
        raise ChangeNotApplicable(
            "campaigns are not applied to Shopware in this deployment — stage a promotion "
            "or listing update instead"
        )

    async def get_pending_changes(self, session: MerchantSessionContext) -> list[StagedChange]:
        return self.ledger.pending()

    async def apply_change(self, session: MerchantSessionContext, change_id: str) -> StagedChange:
        change = self.ledger.get(change_id)
        if change is None:
            raise ChangeNotApplicable(f"no change with id {change_id!r} to apply")
        if violations := check_guardrails(change.kind, change.items, self._config):
            raise GuardrailViolation(violations)
        try:
            notes = await self._writer.apply(change)
        except WriteFailed as error:
            raise ChangeNotApplicable(
                f"the store did not accept change {change_id}: {error}. It is still staged."
            ) from error
        applied = self.ledger.apply(change_id, session.operator)
        if notes:
            applied.guardrail_notes = [*applied.guardrail_notes, *notes]
        return applied

    async def discard_change(
        self,
        session: MerchantSessionContext,
        change_id: str,
        actor_kind: ActorKind = ActorKind.OPERATOR,
    ) -> StagedChange:
        return self.ledger.discard(change_id, session.operator, actor_kind)

    async def get_merchant_context(self, session: MerchantSessionContext) -> dict[str, Any] | None:
        return {
            "store": self.store_name,
            "currency": "EUR",
            "limitations": [
                {
                    "source": "admin-api",
                    "note": "Traffic and marketing campaigns are not read from Shopware.",
                }
            ],
        }

    async def _ensure_catalog(self) -> None:
        if not self.catalog.cached():
            await self.catalog.refresh()

    async def _require_record(self, listing_id: str) -> ProductRecord:
        record = await self.catalog.get(listing_id)
        if record is None:
            raise ChangeNotApplicable(f"listing {listing_id} is not in the Shopware catalog")
        return record

    def _iter_stock_rows(self) -> list[ProductRecord]:
        rows: list[ProductRecord] = []
        for record in self.catalog.cached():
            if record.children:
                rows.extend(record.children)
            else:
                rows.append(record)
        return rows
