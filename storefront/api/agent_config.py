# Copyright 2026 shopware AG
# SPDX-License-Identifier: MIT

"""Shopping-agent config for the Shopware storefront. Identity never travels in
tool arguments; IDs are Shopware hex UUIDs."""

from __future__ import annotations

from shopping_agent import ShoppingAgentConfig

_SHOPWARE_UUID = r"\b[0-9a-f]{32}\b"


def build_shopping_config(store_name: str) -> ShoppingAgentConfig:
    return ShoppingAgentConfig(
        brand_name=store_name,
        assistant_name="the store assistant",
        brand_voice="friendly, direct, and plain about what this Shopware store carries",
        enable_disclosures=True,
        domain_search_notes=(
            "The catalog is a live Shopware 6 shop priced in EUR. A product with options "
            "is a family; purchasable SKUs are its variants in get_product_details. The "
            "cart holds variants (or simple products without options). Checkout, shipping, "
            "and payment happen on the shop's own checkout page — hand the customer to it "
            "rather than promising to place an order. German mandatory facts (Grundpreis, "
            "delivery time, VAT) come from get_disclosure, not from the product description. "
            "Order lookups cover the orders placed with this session's cart (or the linked "
            "Shopware account); for anything older point the customer at their Shopware "
            "confirmation email or account."
        ),
        product_id_patterns=(_SHOPWARE_UUID,),
    )
