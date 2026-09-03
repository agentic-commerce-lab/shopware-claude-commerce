# Storefront web UI

Next.js 16 grid, cart drawer, and assistant rail on top of the shared UI in `vendor/web-shared`
(read-only, vendored from upstream `examples/web-shared`). Talks to the Shopware storefront API on
port 8004.

![Storefront with the cart panel open](../../docs/screenshots/storefront.png)

## Run

```bash
# from the repo root
npm install
npm run dev:storefront        # http://localhost:3005
npm run build -w storefront/web
```

| Variable | Default | Purpose |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8004` | Origin of the storefront API; every call goes to `${NEXT_PUBLIC_API_URL}/api/...`. |

Chat needs `ANTHROPIC_API_KEY` on the API side. Grid, cart, and checkout work without it.

## What it calls

Shared routes (`vendor/demo_common`), through `AgentApi` from `web-shared`:

- `POST /api/session`, `POST /api/chat` (SSE), `GET /api/products`, `GET /api/products/{id}`, `GET /api/cart`, `GET/PATCH /api/memory`

Shopware-specific routes (`storefront/api/main.py`):

| Route | Used by | Notes |
|---|---|---|
| `GET /api/cart`, `POST /api/cart/add` | `StoreShell`, `ProductTile` | The cart payload carries `checkout_url` and `cart_id`; a `cart_update` chat event keeps both from the last read. |
| `POST /api/cart/attach` | `StoreShell` (`?cart=<id>` or `sessionStorage`) | Binds the session to an existing Shopware cart (context token). 404 → the id is dropped. |
| `GET /api/auth/status` | `lib/session.ts` | Revalidates a stored session id on load and drives the signed-in badge. |
| `GET /api/auth/shopware/start` | `Header` → `signIn()` | Answers `{ authorization_url }`; the app leaves with `window.location.assign`. |
| `POST /api/auth/signout` | signed-in badge | Drops the Identity Linking token for the session. |
| `GET /api/brand` | `StoreShell`, `Header` | Store name, tagline, logo, and brand colours (`--brand`, `--brand-contrast`). |

Product ids are Shopware's 32-hex UUIDs; prices are EUR and rendered with `de-DE` formatting via
`lib/format.ts` (the shared `formatMoney` is en-US/USD, so the app never uses it).

## Checkout handoff

"Checkout in Shopware" (cart drawer and the assistant's checkout card) is a plain `<a href>` to
`cart.checkout_url`, opened **in the same tab**. The URL points at the storefront API's own handoff
page (`GET /api/checkout/continue/<ticket>`), which auto-submits a POST form to Shopware's checkout.
A `fetch`, a popup, or `target="_blank"` would not follow that form, so the link stays a normal
navigation. `isSafeCheckoutUrl` only lets `http(s):` URLs through. Nothing is charged in the agent.

## Identity Linking

`Sign in` fetches the authorization URL for the current session and navigates there. Shopware's
OAuth callback returns to `WEB_APP_URL` (`http://localhost:3005`) with `?signed_in=1` (or `0`); the
app shows a short notice, refreshes `/api/auth/status`, and cleans the query string. The session id
lives in `sessionStorage` so it survives the round trip.

## web-shared deltas this app adapts to

- `new AgentApi(root, prefix)` — two arguments; `api.startSession()` resolves `{ sessionId, ... }`.
- `Chat` renders only the transcript; the input is `Composer` (`web-shared/Composer`), which the
  rail mounts itself. `ActivityButton` is imported from `web-shared/ActivityButton`.
- `globals.css` imports `web-shared/base.css` and defines the full token set the shared components
  read (`--ground`, `--chrome`, `--ink-2`, `--line-strong`, `--accent-ink`, shadows, …).

## Files

| Path | Role |
|---|---|
| `app/page.tsx`, `app/products/[id]/page.tsx` | Grid and product detail |
| `components/StoreShell.tsx` | Session, brand, cart state, chat events, sign-in callback |
| `components/Header.tsx` | Brand, sign-in / signed-in badge, activity, cart, assistant toggles |
| `components/CartDrawer.tsx` | Cart lines, quantity, "Checkout in Shopware" |
| `components/Assistant.tsx` | Rail: shared `Chat` + `Composer`, generative cards |
| `components/generative/*` | Product strip, comparison, checkout, order status, plan, guide cards |
| `lib/api.ts`, `lib/session.ts`, `lib/format.ts`, `lib/types.ts` | API client, session, EUR formatting, payload types |
