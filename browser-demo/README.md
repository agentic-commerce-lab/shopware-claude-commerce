# Browser demo — Shopware × Claude Commerce Agents in the browser

Zero-install demo of the same stack as the Docker quick start: **Shopware 6.7.13.1** runs entirely in the tab (PHP WASM + MariaDB WASM via [FriendsOfShopware/shopware-playground](https://github.com/FriendsOfShopware/shopware-playground)), with UCP/MCP plugins and the blueprint shopping and merchant agents on **Pyodide**. A small local Node server serves the static site with cross-origin isolation (COOP/COEP) and proxies the Anthropic API so the key never ships to the browser.

**Status: work in progress.** The build pipeline, WASM shop bundle, Pyodide agent host, overlay UI, and local server are implemented and unit-tested (`npm test`, 13 tests). End-to-end chat turns and checkout handoff still need manual verification after each build; cold boot is slow (~20–40 s on a typical laptop, ~155 MB of downloads). This is not yet a polished public demo — expect rough edges.

Feasibility measurements (2026-09-03) that motivated this tree: [`docs/browser-demo-feasibility.md`](../docs/browser-demo-feasibility.md).

## What works today

| Piece | Status |
|---|---|
| Build pipeline (`npm run build`) | Fetches playground @ pinned commit, installs Shopware + our plugins, seeds in Node PHP WASM, bundles MEMFS zip, syncs Python backends, builds Pyodide wheels, assembles `dist/site` |
| Shopware in WASM | Storefront, Store API, Admin API, UCP discovery, UCP MCP (14 tools), Admin MCP with `dryRun` upserts — same pins as `docker/bootstrap.sh` |
| Demo shell | React app: boot progress, Shopware iframe, shopping / merchant agent panels (vendored Next.js UIs), overlay links in the storefront |
| Anthropic access | Same-origin proxy at `/api/anthropic/*` (key from repo `.env`) or bring-your-own-key in the UI |
| Local server | COOP/COEP on every response, correct WASM MIME types, service-worker scope for Shopware routes |

## Prerequisites

From the repo root (or this folder):

- **Node 22+**, **npm**
- **git**, **zip**, **rsync**
- **PHP ≥ 8.2** with **Composer** (Shopware install step)
- **Python ≥ 3.11** with **pip** (wheel build for Pyodide)
- Network (GitHub, Packagist, PyPI, Pyodide CDN) for the first `npm run build`

## Quick start

```bash
cd browser-demo
npm install
npm run build          # one-time; 10–30+ min depending on cache — see build/build.mjs
cp ../.env.example ../.env   # add ANTHROPIC_API_KEY for proxied chat (optional: BYOK in the UI)
npm start              # → http://127.0.0.1:4188
```

For UI development on an already-built site:

```bash
npm run dev            # Vite middleware + same server routes, HMR for app/src
```

`npm start` requires `dist/site/` (produced by `npm run build`). Individual pipeline steps are exposed as `npm run build:*` — see `package.json`.

## URLs (default server)

| What | URL | Notes |
|---|---|---|
| Demo shell | http://127.0.0.1:4188/ | Boot screen → Shopware iframe + agent panels |
| Shopware storefront (in iframe) | same origin, `/index.php` | Rendered by PHP WASM after boot |
| Shopware admin | `/admin` | `admin` / `Shopware123!` (playground default) |
| UCP discovery | `/.well-known/ucp` | Through the service worker → WASM worker |
| Anthropic proxy | `/api/anthropic/messages` | Server-side key from repo `.env`; budget per tab session |
| Proxy status | `/api/anthropic/status` | Whether a key is configured |

Bind address and port: `--host` / `--port` or `HOST` / `PORT` (default `127.0.0.1:4188`). Use `--host 0.0.0.0` for LAN demos.

## Layout

```text
browser-demo/
├── app/                 React shell (Vite): boot UI, iframe, shopping/merchant views
├── build/               Pipeline scripts (pins in build/config.mjs)
├── host/                Pyodide bootstrap + synced Python backends (build output)
├── plugins/DemoOverlay/ Shopware plugin: storefront overlay + demo context JSON route
├── server/              Local static server + Anthropic proxy (Node built-ins only)
├── scripts/             sync-backends.sh (copies storefront/merchant/api from repo)
└── dist/site/           Assembled demo (gitignored; produced by npm run build)
```

## Testing

```bash
npm test                 # server + build unit tests (no WASM boot)
npm run typecheck        # TypeScript for app/
npm run e2e              # Playwright (requires built site + browser; optional)
```

Repo-wide offline tests (`pytest`, `ruff`) do not cover this tree; `ruff check .` may report findings under `host/`.

## Configuration

The server reads `../.env` (repo root) then `browser-demo/.env`. Relevant variables:

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Enables the proxied chat path (otherwise BYOK only) |
| `ANTHROPIC_WORKSPACE_ID` | Identity-linked keys |
| `DEMO_PROXY_*` | Per-session / per-IP budgets — see `server/anthropic-proxy.mjs` |
| `PORT`, `HOST` | Listen address (default `4188`, `127.0.0.1`) |

Build-time pins (playground commit, plugin refs, Pyodide version): `build/config.mjs`.

## Not in this demo yet

- Parity with every Docker quick-start flow (identity linking over https, full eval gate, nightly CI on WASM)
- Hosted static deployment (R2/CDN packaging exists upstream in shopware-playground; not wired here)
- Merchant portal at a separate origin — both agents share the demo shell on `:4188`
