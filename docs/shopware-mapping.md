# Shopware mapping (spikes A–C)

Discovered against dockware **Shopware 6.7.13.0** + `SwagAgenticCommerce`. Protocol version **2026-04-08**.

## Transports

| Transport | Endpoint | When used |
|---|---|---|
| Discovery | `GET /.well-known/ucp` | Profile, capabilities, service URLs |
| REST (default) | `/ucp/v1/*` | Storefront backend (`UCP_TRANSPORT=rest`) |
| MCP | `POST /ucp/mcp` (Store API `/store-api/_mcp`) | Fallback if REST 404/405 without a UCP error document |
| Embedded | checkout iframe origins | Not used; we hand off |

Required header: `UCP-Agent: platform; profile="http://localhost/agent-profile.json"` (the shop fetches this URL **from inside Docker**, so the host must be reachable on container port 80 — not host `:8080`). Writes also send `Idempotency-Key`. Local policy is `signature-policy=log` (unsigned accepted). `SWAG_AGENTIC_COMMERCE_UCP_PROFILE_FETCHING_DEVELOPMENT_MODE=1` allows http profiles. Allowlist hosts: `localhost` and `127.0.0.1`. The agent profile must declare the same capability names as the shop (`dev.ucp.shopping.catalog`, `.cart`, `.checkout`, `.order`, `.discount`, `dev.ucp.common.identity_linking`) as **lists**, or Shopware returns `capabilities_incompatible`.

## Agent profile (local Docker)

Shopware fetches `UCP-Agent` `profile="..."` **from inside the container**. Use `http://localhost/agent-profile.json` (Apache on :80). Host `:8080` is not reachable from the shop process.

Repo `agent-profile.json` must declare the same capability names as the shop, as **lists** (not objects). A missing intersection returns `capabilities_incompatible`. Bootstrap copies the file into `public/` and sets `SWAG_AGENTIC_COMMERCE_UCP_PROFILE_FETCHING_DEVELOPMENT_MODE=1` so http localhost is allowed. Recreating the container wipes plugin files; re-run `./docker/bootstrap.sh`.

## REST paths

| Operation | HTTP |
|---|---|
| catalog.search | `POST /ucp/v1/catalog/search` `{query, limit}` |
| catalog.lookup | `POST /ucp/v1/catalog/lookup` `{ids}` |
| catalog.product | `GET /ucp/v1/catalog/product/{id}` |
| cart.create | `POST /ucp/v1/carts` |
| cart.get | `GET /ucp/v1/carts/{id}` |
| cart.update | `PATCH /ucp/v1/carts/{id}` replace-all `line_items` |
| cart.cancel | `POST /ucp/v1/carts/{id}/cancel` |
| checkout.create | `POST /ucp/v1/checkout-sessions` |
| checkout.get/update | `GET` / `PATCH /ucp/v1/checkout-sessions/{id}` |
| checkout.complete | `POST .../complete` — **never called** |
| order.get | `GET /ucp/v1/orders/{id}` |

## MCP tool names (not Shopify names)

Mutating MCP tools default to `dryRun=true` on the server. This client sends `dryRun=false` for real cart/checkout writes.

MCP `tools/list` requires a session: `initialize` then `Mcp-Session-Id` on later calls. Live list on 6.7.13 + SwagAgenticCommerce 1.3.0:

| Our name | Shopware MCP tool |
|---|---|
| (Store API context) | `shopware-store-api-context` |
| search_catalog | `shopware-ucp-catalog-search` |
| lookup_catalog | `shopware-ucp-catalog-lookup` |
| create_cart | `shopware-ucp-cart-create` |
| update_cart | `shopware-ucp-cart-update` |
| get_cart | `shopware-ucp-cart-get` |
| cancel_cart | `shopware-ucp-cart-cancel` |
| create_checkout | `shopware-ucp-checkout-create` |
| update_checkout | `shopware-ucp-checkout-update` |
| get_checkout | `shopware-ucp-checkout-get` |
| complete_checkout | `shopware-ucp-checkout-complete` |
| cancel_checkout | `shopware-ucp-checkout-cancel` |
| apply_discount | `shopware-ucp-discount-apply` |
| get_order | `shopware-ucp-order-get` |

On 6.7.13 MCP needs the `MCP_SERVER=1` feature flag (bootstrap sets it). REST UCP works without it.

## Spike B — cart id

Shopware's UCP cart `id` is the sales-channel context token (Store API `sw-context-token`). On 6.7.13 + plugin 1.3.0 the token looks like a ULID (`01a0…`), not a Shopify GID. `ShopwareDataMapper` uses `$cart->getToken() ?: $context->getToken()`.

## Spike C — checkout

Checkout is a **handoff**. Staging `create_checkout` still runs (Shopware session). The URL the host opens is:

`{shop}/claude-commerce/continue?token={cartId}`

`cartId` is the Store API context token. Plugin `CommerceAgentsHandoff` writes it into the storefront session and redirects to `/checkout/confirm`. A raw `continue_url` of `/checkout/confirm?checkoutId=…` does **not** restore the cart in the browser (different cookie).

The agent never calls `complete_checkout` unless `SHOPWARE_AGENT_COMPLETE_CHECKOUT=1` (documented opt-in, default off). Payment stays on the Shopware storefront.

## IDs and catalog

- Product / variant ids are 32-char hex UUIDs (`\b[0-9a-f]{32}\b`).
- UCP product documents are often thin (no full variant matrix). The backend enriches via Store API `POST /store-api/product/{id}` with `children`, `options.group`, `deliveryTime`, `unit`, `calculatedPrice.referencePrice` (Grundpreis).
- One out-of-stock variant raises `Unavailable` and lists in-stock sibling ids.

## Merchant Admin

- Auth: password grant (`client_id=administration`) or integration `client_credentials`.
- Reads: `POST /api/search/product`, `POST /api/search/order`.
- Writes (apply only): `PATCH /api/product/{id}` for name/description/price/stock/active.
- Optional preview: `POST /api/_mcp` tool `shopware-entity-upsert` with `dryRun=true` when `SHOPWARE_ADMIN_TRANSPORT=mcp`.

## Store API gaps

Policies (footer CMS, `/agents.md`, `/llms.txt`), disclosures (PAngV Grundpreis, Lieferzeit, MwSt.), fulfillment (shipping methods), brand (sales-channel context). Fallback German copy lives in `storefront/api/policies.py` when the shop has no CMS pages.
