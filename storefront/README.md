# Storefront shopping agent

FastAPI host implementing Anthropic's `StorefrontBackend` against a live Shopware UCP surface (MCP first, REST fallback, RFC 9421 signed), plus a Next.js grid / cart / assistant UI on the blueprint's `web-shared`.

```
storefront/api/
  ucp_client.py       UcpClient — MCP (shopware-ucp-* tools) primary, /ucp/v1 REST fallback, signing, idempotency
  shopware_backend.py StorefrontBackend: catalog, variants, cart, handoff, orders, policies, disclosures, fulfillment
  store_api.py        Store API client (typed StoreApiError): product/children, shipping methods, navigation, CMS, orders, context
  handoff.py          HandoffBroker — per-session ticket → one-time signed code → auto-POST page for the plugin
  identity.py         UCP Identity Linking (OAuth authorization code + PKCE) against the shop's AS
  policies.py         PolicyIndex over CMS footer/service pages, /agents.md, /llms.txt, fallback copy
  disclosures.py      PAngV base price, delivery time, VAT rows from Store API data + fixed copy
  brand.py            shop name / locale / currency for the web UI
  catalog_warmup.py   grid products entered into provenance at session start
  main.py             FastAPI host (routes below)
  tests/              netless replay of UCP over MCP + REST, Store API, OAuth AS; runs every test on both transports
storefront/data/      recorded UCP fixtures, discovery document, disclosure_copy.de.json
storefront/scripts/smoke.py   live checks over both transports
storefront/web/       Next.js UI on :3005 (see web/README.md)
```

## API

```bash
# from repo root, venv active; docker/.generated.env is read for every variable .env leaves empty
uvicorn storefront.api.main:app --port 8004
```

| Route | Purpose |
|---|---|
| `GET /api/health` | process check (no Anthropic key) |
| `POST /api/session` | start a shopping session; warm-up grid products enter provenance |
| `GET /api/products` | display cache (filled by search / warm-up) |
| `POST /api/cart/add` | direct add — runs `get_product_details` through the executor first, so the provenance gate holds |
| `POST /api/cart/attach` | adopt an existing Shopware context token as this session's cart |
| `GET /api/cart` | cart plus `checkout_url` (a ticket URL on this host; **no write to Shopware on GET**) |
| `GET /api/checkout/handoff/{ticket}` | mints a one-time handoff code (≤ 120 s, HMAC-signed, AES-GCM-boxed context token) and answers an HTML page that auto-submits `POST {shop}/claude-commerce/continue` |
| `GET /api/auth/shopware/start`, `POST /api/auth/shopware/login`, `GET /api/auth/status`, `POST /api/auth/signout` | UCP Identity Linking (Shopware's platform-to-shop OAuth code + PKCE: the customer logs in via `POST /store-api/account/login`, the host signs the authorize call and exchanges the code; no browser hop); `start` answers 503 with the reason while the agent profile is not served over https |
| `GET /api/brand` | shop name, locale, currency, accent for the web UI |
| `GET /agent-profile.json` | the UCP agent profile (with the published signing key) |
| `POST /api/chat` | SSE turn; needs `ANTHROPIC_API_KEY` (identity-linked keys also `ANTHROPIC_WORKSPACE_ID`, sent as `anthropic-workspace-id` by `shopware_common/anthropic_client.py`) |

### Environment

| Variable | Default | Meaning |
|---|---|---|
| `SHOPWARE_URL` | `http://localhost:8080` | sales-channel domain serving `/.well-known/ucp` |
| `SHOPWARE_SALES_CHANNEL_ACCESS_KEY` | from `docker/.generated.env` | Store API `sw-access-key` |
| `UCP_TRANSPORT` | `mcp` | `mcp` or `rest`; the other one is the fallback for transport-level failures |
| `UCP_AGENT_PROFILE_URL` | `http://localhost/agent-profile.json` | what the shop fetches (from inside the container) |
| `UCP_AGENT_SIGNING_KEY_PEM_FILE` | from `docker/.generated.env` | P-256 key for RFC 9421 + 9530 signatures (repo-root relative) |
| `COMMERCE_AGENTS_HANDOFF_SECRET` | from `docker/.generated.env` | shared with the `CommerceAgentsHandoff` plugin; unset disables the handoff (logged) |
| `STOREFRONT_API_PUBLIC_URL` | `http://localhost:8004` | how the browser reaches this host (ticket URL, OAuth redirect) |
| `SHOPWARE_UCP_OAUTH_CLIENT_ID`, `SHOPWARE_OAUTH_REDIRECT_URI` | profile URL / `{public}/api/auth/shopware/callback` | Identity Linking client id (must be https) and the `redirect_uri` sent to the AS (the code is returned in the JSON body, so no route listens there) |
| `WEB_APP_URL`, `BRAND_TAGLINE`, `CATALOG_WARMUP` | `http://localhost:3005`, tagline, `1` | web UI wiring |

### Shopware facts the backend relies on

- The UCP cart id **is** the Store API context token; one cart per session, never in a URL, never shown to the model.
- MCP tool results are wrapped in `{"success", "dryRun", "data"}`; the client unwraps them so both transports yield the same document.
- `GET /ucp/v1/catalog/product/{family}` and `GET /store-api/product/{family}` both answer a *child* (the Store API child carries `parentId == family`); the backend uses that to tell families from variants. Real children (including out of stock) come from `POST /store-api/product` filtered by `parentId`.
- A guest cart that has not ordered gets `403 CHECKOUT__CUSTOMER_NOT_LOGGED_IN` from `POST /store-api/order` → empty order list.

## Web

```bash
npm install
npm run dev:storefront
```

Opens http://localhost:3005 against `NEXT_PUBLIC_API_URL` (default http://localhost:8004). "Checkout in Shopware" opens the ticket URL in the same tab, which lands on Shopware's confirm page with the same cart. Details in [`web/README.md`](web/README.md).

## Tests and smoke

```bash
pytest storefront/api/tests                       # netless; every backend test runs over MCP and over REST
python storefront/scripts/smoke.py                # live: both transports, signed when the key is configured
python storefront/scripts/smoke.py --transport mcp --no-fallback
```

`smoke.py` runs discovery, `tools/list`, search, details with variants, add / update / remove on a real cart, fulfillment options, policy search, orders behind the cart token, and the handoff round trip (mint → POST to the plugin → 302 to `/checkout/confirm`; replay refused).
