# Progress

Shopware × Claude Commerce Agents — phases 0–2 complete and stabilized (2026-09-03).

## Phase 0 — Docker Shopware + UCP

- [x] Repo layout (`storefront/`, `merchant/`, `shopware_common/`, `vendor/`, `docker/`)
- [x] `docker/compose.yaml` + `docker/bootstrap.sh` (dockware/shopware 6.7.13.0, `MCP_SERVER=1`)
- [x] Shopware container healthy on `:8080`
- [x] Install + activate `SwagAgenticCommerce` and `SwagMcpMerchantTools` — **pinned to commits** (ADR-11, see `docs/version-matrix.md`)
- [x] Enable UCP on Storefront (catalog, cart, discount, checkout, order, identity_linking; rest + mcp + embedded) via `ucp:config:set`
- [x] Shop signing key: exactly one active key after repeated bootstraps
- [x] Agent signing key `secrets/ucp-agent-signing-key.pem`, JWK published in `agent-profile.json`, `signature-policy=strict`
- [x] Seed catalog (CA-TSHIRT S/M/L with L OOS, CA-OIL Grundpreis), delivery times, shipping prices, CMS policy pages, order history
- [x] Merchant identity: integration + ACL role `claude-merchant-agent` + Admin MCP allowlist (ADR-14)
- [x] `docker/verify.sh`; bootstrap re-runnable without side effects (M10)
- [x] `curl /.well-known/ucp` returns a profile (2026-04-08)
- [x] Live facts documented in `docs/shopware-mapping.md`

## Phase 1 — Storefront shopping agent

- [x] Blueprint packages pinned in `requirements.txt`
- [x] `vendor/` with NOTICE (vendored Anthropic/Shopify material stays Apache-2.0; this repo's own code is MIT, `Copyright 2026 shopware AG`)
- [x] `storefront/api` FastAPI host + Shopware `StorefrontBackend`
- [x] UCP client: **MCP primary, REST fallback** (ADR-12 rev.), real Streamable-HTTP client in `shopware_common/mcp_client.py`
- [x] RFC 9421 + RFC 9530 request signing (`shopware_common/http_signing.py`), verified by the netless replay and the strict shop
- [x] Variant handling: family vs child, real children incl. out of stock, `Unavailable` with siblings (H1/H2)
- [x] Orders from the Store API behind the cart token / linked customer (H3)
- [x] Store API gaps: policies from CMS pages (M6), disclosures, fulfillment with fees + ETA (M5), variants by `parentId`
- [x] Checkout handoff via one-time HMAC-signed code, POST auto-submit, never the raw token (ADR-10, K2); no `complete_checkout` path; no writes on `GET /api/cart` (M4)
- [x] Direct add establishes provenance through the executor (H7)
- [x] Typed `StoreApiError` with logging (M9)
- [x] Identity Linking (OAuth code + PKCE) implemented; 503 with reason on the http-only Docker shop
- [x] Next.js storefront on `web-shared` (grid, cart, assistant rail, checkout button, brand from the shop)
- [x] pytest with netless replay of UCP (MCP + REST), Store API, OAuth AS
- [x] `storefront/scripts/smoke.py` against the live shop over both transports (search → details/variants → cart → fulfillment → policies → orders → handoff)
- [x] Browser: grid → add to cart → Checkout in Shopware (`docs/screenshots/storefront.png`)

## Phase 2 — Merchant agent

- [x] `AdminTransport` protocol: `McpTransport` (default) + `RestTransport` (fallback) (ADR-12 rev., H4/H9)
- [x] Integration `client_credentials` only; admin password removed from the hosts (ADR-14, H8)
- [x] `apply_change` / `discard_change` refuse non-STAGED changes (K1)
- [x] Stage = `shopware-entity-upsert dryRun=true` → `ChangeItem {before, after}` + `guardrail_notes`; apply replays with `dryRun=false`
- [x] Real promotions: `promotion` + `promotion_discount` + rule + sales channel; partial failures reported (ADR-13, H5)
- [x] Price write replaces only the sales-channel currency, net from tax rate (H6)
- [x] Restock as delta on fresh stock (M1); pause/activate expands to children (M2)
- [x] Performance insights from aggregations: snapshot, metrics, inventory alerts, order issues, pricing context (M3)
- [x] SQLite ledger via `MERCHANT_LEDGER_DSN`, survives restarts (M7)
- [x] Portal routes `/api/merchant/dashboard`, `/orders`, `/changes`; listing staged changes admits them to the session's provenance so the portal's Approve / Dismiss works across sessions and restarts
- [x] Merchant portal `merchant/web` on `:3006` mirroring the reference portal (KPI row, Needs you today, assistant rail with staged-change cards, pending count on the sidebar's Assistant entry)
- [x] MCP client hardening from the live pass: one in-flight request per session (Shopware answers one of two concurrent calls with an empty body); offloaded results (`_meta.resourceUri` → `resources/read`) collected instead of read as empty — this is what fills the portal's recent-orders feed
- [x] pytest (transports, staging, ledger, portal) + `merchant/scripts/smoke_live.py` (read-only and `--write` round trips over MCP and REST)
- [x] Browser: dashboard → briefing → stage price → approve → verified in Shopware → reverted (`docs/screenshots/merchant-portal.png`)

## Housekeeping

- [x] `vendor/demo_common`, `vendor/web-shared`, skills re-vendored byte-identical from `fd4d5922`; NOTICE lists the adapted `merchant/web` files (M8)
- [x] `.env.example` cleaned (no admin password, no `SHOPWARE_AGENT_COMPLETE_CHECKOUT`, MCP defaults)
- [x] MASTERPLAN §4.2 records ADR-10 … ADR-14; `docs/shopware-mapping.md` carries the live tool names and schemas
- [x] `pytest -q`, `ruff check .`, `ruff format --check .`, `npm run build` green

## Phase 3 — not started

- [ ] Claude Code plugin, evals, Managed Agents manifests
- [ ] CI workflow
- [ ] Identity Linking end to end (needs an https agent profile; the code path exists)
- [ ] Per-line-item promotion scoping
