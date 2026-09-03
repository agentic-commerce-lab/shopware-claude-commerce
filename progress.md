# Progress

Shopware × Claude Commerce Agents — first working version.

## Phase 0 — Docker Shopware + UCP

- [x] Repo layout (`storefront/`, `merchant/`, `vendor/`, `docker/`)
- [x] `docker/compose.yaml` + `docker/bootstrap.sh` (dockware/shopware 6.7.13.0)
- [x] Shopware container healthy on `:8080`
- [x] Install + activate `SwagAgenticCommerce` (v1.3.0) and `SwagMcpMerchantTools`
- [x] Enable UCP on Storefront (catalog, cart, discount, checkout, order, identity_linking; rest + mcp + embedded)
- [x] Signing keys + `signature-policy=log`
- [x] Seed catalog (CA-TSHIRT S/M/L with L OOS, CA-OIL Grundpreis)
- [x] `curl /.well-known/ucp` returns a profile (2026-04-08)
- [x] Spikes A–C documented in `docs/shopware-mapping.md` from live inspection

## Phase 1 — Storefront shopping agent

- [x] Blueprint packages pinned in `requirements.txt`
- [x] `vendor/` with NOTICE (vendored Anthropic/Shopify material stays Apache-2.0; this repo's own code is MIT, `Copyright 2026 shopware AG`)
- [x] `storefront/api` FastAPI host + Shopware `StorefrontBackend`
- [x] UCP client (REST primary, MCP fallback)
- [x] Store API gaps: policies, disclosures, fulfillment, variant listing by `parentId`
- [x] Checkout handoff (`continue_url`); never `complete_checkout`
- [x] Next.js storefront (grid, cart, assistant rail, checkout button)
- [x] pytest with recorded fixtures (no network) — 40 passed
- [x] `storefront/scripts/smoke.py` against live Docker shop (search → details/variants → cart → handoff)
- [x] Browser: grid → add to cart → Check out on Shopware → guest register with CA-TSHIRT in cart

## Phase 2 — Merchant agent

- [x] Admin REST transport (+ MCP dry-run when `SHOPWARE_ADMIN_TRANSPORT=mcp`)
- [x] Staging ledger; `POST /changes/{id}/apply`
- [x] pytest + `merchant/scripts/smoke_live.py --read-only`

## Phase 3 — Claude Code plugin

- [ ] Skipped until 1+2 are solid (they are; plugin still out of this first version)

## Stubbed

- Identity Linking (503 without OAuth client; guest path works)
- RFC 9421 signing (log policy locally)
- Merchant campaigns / live promotions
- Claude Code plugin
- Chat streaming without `ANTHROPIC_API_KEY`
