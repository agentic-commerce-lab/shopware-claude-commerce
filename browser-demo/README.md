# Browser demo — Shopware × Claude Commerce Agents in the browser

**[Open the live demo](https://sthamann.github.io/shopware_claude_commerce/)** — click that link; nothing to install.

Shopware 6.7.13.1 runs in the tab (PHP WASM + MariaDB WASM via [FriendsOfShopware/shopware-playground](https://github.com/FriendsOfShopware/shopware-playground)). The blueprint shopping and merchant hosts run on **Pyodide**. GitHub Actions builds the gitignored WASM shop and publishes the static tree to GitHub Pages.

Cold boot downloads ≈ 150 MB and takes ~20–40 s on a typical laptop. A reload reuses the browser cache and the seeded database in IndexedDB. Use a current desktop Chromium or Firefox (service workers + SharedArrayBuffer). Mobile is not sensible.

## What the Pages build does

| Piece | On GitHub Pages |
|---|---|
| Demo shell (boot UI, shop iframe, agent panels) | Yes |
| Shopware storefront / admin / Store API / UCP / MCP in WASM | Yes, after the boot download (same pins as `docker/bootstrap.sh`) |
| Catalog, cart, seeded products and orders | Yes |
| Chat (Claude) | Only if you paste an `ANTHROPIC_API_KEY` in the UI. Pages cannot run the Node proxy. The tab calls `api.anthropic.com` with `anthropic-dangerous-direct-browser-access`. If Anthropic rejects that browser request, chat fails; the shop still works. |
| Checkout handoff / full Docker parity | Implemented in the shell; treat as WIP until verified on a fresh Pages build |
| Cross-origin isolation | GitHub Pages cannot set COOP/COEP. The playground service worker adds those headers; the shell reloads once so `SharedArrayBuffer` works. |

The first [pages.yml](../.github/workflows/pages.yml) run takes 10–30+ minutes. Until it has succeeded, the live URL may 404.

Feasibility measurements: [`docs/browser-demo-feasibility.md`](../docs/browser-demo-feasibility.md).

## Run locally (contributors)

The local Node server is optional. It sets COOP/COEP without a service-worker reload and can proxy Anthropic from the repo `.env` so the key never enters the tab.

```bash
cd browser-demo
npm install
npm run build          # first time: PHP, Composer, Python, network (~10–30+ min)
cp ../.env.example ../.env   # ANTHROPIC_API_KEY for the local proxy (optional)
npm start              # → http://127.0.0.1:4188
```

`npm run dev` is Vite HMR against an already-built playground. `npm start` needs `dist/site/` from `npm run build`. Individual steps: `npm run build:*` in `package.json`.

A Pages-shaped local tree (project path prefix):

```bash
DEMO_BASE_PATH=/shopware_claude_commerce/ npm run build:app
DEMO_BASE_PATH=/shopware_claude_commerce/ npm run build:site
```

That prefix is what [pages.yml](../.github/workflows/pages.yml) sets from `actions/configure-pages`.

| What | Local URL |
|---|---|
| Demo shell | http://127.0.0.1:4188/ |
| Shopware storefront (iframe) | `/index.php` after boot |
| Anthropic proxy (local only) | `/api/anthropic/messages` |
| Proxy status | `/api/anthropic/status` |

Bind address: `--host` / `--port` or `HOST` / `PORT` (default `127.0.0.1:4188`).

## Layout

```text
browser-demo/
├── app/                 React shell (Vite): boot UI, iframe, shopping/merchant views
├── build/               Pipeline scripts (pins in build/config.mjs)
├── host/                Pyodide bootstrap + synced Python backends (build output)
├── plugins/DemoOverlay/ Shopware plugin: storefront overlay + demo context JSON route
├── server/              Local static server + Anthropic proxy (contributors)
├── scripts/             sync-backends.sh (copies storefront/merchant/api from repo)
└── dist/site/           Assembled demo (gitignored; produced by npm run build / CI)
```

## Testing

```bash
npm test                 # server + build unit tests (18; no WASM boot)
npm run typecheck        # TypeScript for app/
npm run e2e              # Playwright (requires built site + browser; optional)
```

Repo-wide offline tests (`pytest`, `ruff`) do not cover this tree; `ruff check .` may report findings under `host/`.

## Configuration

The local server reads `../.env` (repo root) then `browser-demo/.env`. Relevant variables:

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Enables the local proxied chat path (otherwise paste a key in the UI) |
| `ANTHROPIC_WORKSPACE_ID` | Identity-linked keys |
| `DEMO_PROXY_*` | Per-session / per-IP budgets — see `server/anthropic-proxy.mjs` |
| `PORT`, `HOST` | Listen address (default `4188`, `127.0.0.1`) |
| `DEMO_BASE_PATH` | Public path for the assembled site (`/` locally, `/shopware_claude_commerce/` on Pages) |

Build-time pins (playground commit, plugin refs, Pyodide version): `build/config.mjs`.

## Not in this demo yet

- Parity with every Docker quick-start flow (identity linking, full eval gate, nightly CI on WASM)
- A hosted Anthropic proxy — GitHub Pages cannot run one; do not expect chat without your own key
- Merchant portal at a separate origin — both agents share the demo shell
