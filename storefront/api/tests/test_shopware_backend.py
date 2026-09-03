# Copyright 2026 Shopware × Claude Commerce Agents authors.
# SPDX-License-Identifier: Apache-2.0

"""Shopware storefront backend over recorded UCP REST documents."""

from __future__ import annotations

from commerce_common.skills import SkillRegistry
from shopping_agent import SearchFilters, ShoppingSessionContext, Unavailable
from shopping_agent.executor import ShoppingToolExecutor
from storefront.api.agent_config import build_shopping_config

from .replay import (
    CART_ID,
    GONE_CART_ID,
    OIL_ID,
    PRODUCT_ID,
    SEARCH_QUERY,
    VARIANT_L,
    VARIANT_S,
)


async def search(backend, session):
    return await backend.search_products(session, SEARCH_QUERY, limit=3)


async def test_search_maps_hex_ids_and_minor_unit_prices(backend, session):
    products = await search(backend, session)
    assert products[0].product_id == PRODUCT_ID
    first = products[0]
    assert first.title == "Claude Commerce T-Shirt"
    assert (first.price, first.currency) == (29.99, "EUR")
    assert first.in_stock
    assert first.image_url == "https://cdn.example/shirt.jpg"


async def test_details_list_variants_including_out_of_stock(backend, session):
    details = await backend.get_product_details(session, PRODUCT_ID)
    assert details is not None
    assert {v.product_id for v in details.variants} >= {VARIANT_S, VARIANT_L}
    sold_out = next(v for v in details.variants if v.product_id == VARIANT_L)
    assert sold_out.in_stock is False
    assert details.specs.get("deliveryTime")


async def test_a_seen_variant_id_resolves_to_its_own_details(backend, session):
    await backend.get_product_details(session, PRODUCT_ID)
    details = await backend.get_product_details(session, VARIANT_S)
    assert details is not None
    assert details.product_id == VARIANT_S
    assert "S" in details.title


async def test_an_unknown_product_id_is_none(backend, session):
    assert await backend.get_product_details(session, "ffffffffffffffffffffffffffffffff") is None


async def test_price_filters_travel_as_minor_units(backend, session, client):
    sent = {}
    original = client.call_ucp

    async def spy(name, arguments, **kwargs):
        sent.update(arguments)
        return await original(name, arguments, **kwargs)

    client.call_ucp = spy
    filters = SearchFilters(min_price=10.0, max_price=50.0)
    await backend.search_products(session, SEARCH_QUERY, filters=filters, limit=3)
    assert sent["catalog"]["filters"] == {"price": {"min": 1000, "max": 5000}}


async def test_the_cart_lifecycle_keeps_one_token_per_session(backend, session):
    assert (await backend.get_cart(session)).items == []

    products = await search(backend, session)
    cart = await backend.add_to_cart(session, products[0].product_id, 1)
    assert [(i.product_id, i.quantity, i.price) for i in cart.items] == [(VARIANT_S, 1, 29.99)]
    assert cart.currency == "EUR"
    checkout = await backend.checkout_url_for(session.session_id)
    assert checkout == f"http://shopware.test/claude-commerce/continue?token={CART_ID}"
    assert backend.cart_id_for(session.session_id) == CART_ID

    assert (await backend.get_cart(session)).item_count == 1
    updated = await backend.update_cart_item(session, VARIANT_S, 2)
    assert updated.item_count == 2
    removed = await backend.remove_from_cart(session, VARIANT_S)
    assert removed.items == []


async def test_adding_a_variant_id_directly_skips_default_resolution(backend, session):
    await search(backend, session)
    cart = await backend.add_to_cart(session, VARIANT_S, 1)
    assert cart.items[0].product_id == VARIANT_S


async def test_out_of_stock_variant_raises_unavailable(backend, session):
    await backend.get_product_details(session, PRODUCT_ID)
    try:
        await backend.add_to_cart(session, VARIANT_L, 1)
        raise AssertionError("expected Unavailable")
    except Unavailable as error:
        assert VARIANT_S in str(error) or "unavailable" in str(error).lower()


async def test_reset_session_drops_the_cart_binding(backend, session):
    await search(backend, session)
    await backend.add_to_cart(session, PRODUCT_ID, 1)
    backend.reset_session(session.session_id)
    assert (await backend.get_cart(session)).items == []
    assert await backend.checkout_url_for(session.session_id) is None


async def test_sessions_do_not_share_carts(backend, session):
    await search(backend, session)
    await backend.add_to_cart(session, PRODUCT_ID, 1)
    other = ShoppingSessionContext(session_id="s-2", user_id="guest")
    assert (await backend.get_cart(other)).items == []


async def test_a_dropped_cart_reads_as_empty_and_unbinds(backend, session):
    await search(backend, session)
    await backend.add_to_cart(session, PRODUCT_ID, 1)
    backend._sessions[session.session_id].cart_id = GONE_CART_ID
    cart = await backend.get_cart(session)
    assert cart.items == []
    assert backend._sessions[session.session_id].cart_id is None


async def test_adding_into_a_dropped_cart_starts_a_fresh_one(backend, session):
    await search(backend, session)
    await backend.add_to_cart(session, PRODUCT_ID, 1)
    backend._sessions[session.session_id].cart_id = GONE_CART_ID
    cart = await backend.add_to_cart(session, PRODUCT_ID, 1)
    assert cart.items[0].product_id == VARIANT_S
    assert backend._sessions[session.session_id].cart_id != GONE_CART_ID


async def test_checkout_handoff_never_completes(backend, session):
    await search(backend, session)
    cart = await backend.add_to_cart(session, PRODUCT_ID, 1)
    handoff = await backend.checkout_handoff(session, cart)
    assert handoff and handoff[0].url == f"http://shopware.test/claude-commerce/continue?token={CART_ID}"
    assert "Shopware" in handoff[0].label


async def test_policies_and_disclosures(backend, session):
    policies = await backend.search_policies(session, "widerruf")
    assert policies
    assert any("Widerruf" in p.title or "widerruf" in p.content.lower() for p in policies)
    disclosure = await backend.get_disclosure(session, PRODUCT_ID)
    assert disclosure is not None
    oil = await backend.get_disclosure(session, OIL_ID)
    assert oil is not None
    assert any("Grundpreis" in row.label or "25,80" in row.value for row in oil.rows)


async def test_fulfillment_options_use_shipping_methods(backend, session):
    options = await backend.get_fulfillment_options(session, [PRODUCT_ID])
    assert options
    assert "Standard" in options[0].eta


def make_executor(backend, session, state) -> ShoppingToolExecutor:
    return ShoppingToolExecutor(
        backend=backend,
        config=build_shopping_config("Shopware"),
        skills=SkillRegistry([]),
        session=session,
        state=state,
    )


async def test_cart_writes_hold_without_provenance_and_pass_with_it(backend, session, state):
    executor = make_executor(backend, session, state)
    held = await executor.execute("add_to_cart", {"product_id": PRODUCT_ID, "quantity": 1})
    assert held.blocked

    await executor.execute("search_products", {"query": SEARCH_QUERY})
    assert PRODUCT_ID in state.seen_products
    details = await executor.execute("get_product_details", {"product_id": PRODUCT_ID})
    assert not details.refused
    added = await executor.execute("add_to_cart", {"product_id": VARIANT_S, "quantity": 1})
    assert not added.refused
    updated = await executor.execute("update_cart_item", {"product_id": VARIANT_S, "quantity": 2})
    assert not updated.refused
    removed = await executor.execute("remove_from_cart", {"product_id": VARIANT_S})
    assert not removed.refused
