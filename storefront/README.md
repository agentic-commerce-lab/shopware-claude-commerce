# Storefront shopping agent

FastAPI host implementing Anthropic `StorefrontBackend` against a live Shopware UCP surface, plus a Next.js grid / cart / assistant UI.

## API

```bash
# from repo root, venv active, docker/.generated.env merged into .env
uvicorn storefront.api.main:app --port 8004
```

- `GET /api/health` — process check (no Anthropic key)
- `POST /api/session` — start a shopping session (grid products from warmup enter provenance so add-to-cart works without a chat turn)
- `GET /api/products` — display cache (filled by search / warmup)
- `POST /api/cart/add` — direct add (provenance gate: product must have been seen)
- `GET /api/cart` — cart plus `checkout_url` (Shopware handoff)
- `POST /api/chat` — SSE turn; 503-style skip without `ANTHROPIC_API_KEY`

UCP REST is default (`UCP_TRANSPORT=rest`). MCP (`/ucp/mcp`, Shopware tool names) is the fallback after `initialize` + `Mcp-Session-Id`. Cart id is the Shopware context token. Checkout is `continue_url` only.

The shop fetches `UCP_AGENT_PROFILE_URL` from inside Docker (`http://localhost/agent-profile.json`). Product detail on a parent SKU often returns the selected variant; variants are loaded with Store API `POST /store-api/product` filtered by `parentId`.

## Web

```bash
npm install
npm run dev:storefront
```

Opens http://localhost:3005 against `NEXT_PUBLIC_API_URL` (default http://localhost:8004). Checkout button opens Shopware's confirm page.

## Tests and smoke

```bash
pytest storefront/api/tests
python storefront/scripts/smoke.py
```

Tests use `httpx.MockTransport` (`api/tests/replay.py`) and never hit the network.

## Files

| Path | Role |
|---|---|
| `api/ucp_client.py` | REST + MCP UCP client |
| `api/shopware_backend.py` | `StorefrontBackend` |
| `api/store_api.py` | Policies, variants, Grundpreis, shipping |
| `api/main.py` | FastAPI host |
| `web/` | Next.js UI (web-shared) |
