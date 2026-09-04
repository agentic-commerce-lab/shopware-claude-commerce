// Copyright 2026 Shopify Inc.
// SPDX-License-Identifier: Apache-2.0

import { AgentApi } from "web-shared";

import type { AuthStatus, Brand, CartPayload, Product, ProductDetails } from "./types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8004";

const TIMEZONE_HEADER = "X-Timezone";

/** The browser's IANA zone, when the runtime knows it (a server render does not). */
function browserTimezone(): string | null {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone ?? null;
  } catch {
    return null;
  }
}

/**
 * The shared client plus the customer's timezone on every request (`X-Timezone`), so the
 * host's session clock is the customer's, not the server's (`shopware_common.clock`).
 */
class TimezoneAwareApi extends AgentApi {
  headers(json = false): Record<string, string> {
    const headers = super.headers(json);
    const zone = browserTimezone();
    if (zone) headers[TIMEZONE_HEADER] = zone;
    return headers;
  }
}

/** The shared client: `root` is the API's origin, the storefront routes live under `/api`. */
export const api = new TimezoneAwareApi(API_URL, "/api");

export const UNREACHABLE =
  "Couldn't reach the storefront host on port 8004. Start it with `uvicorn storefront.api.main:app --port 8004` and try again.";

const GRID_LIMIT = "24";

/** `GET /api/cart`: the shared cart shape plus Shopware's `checkout_url` and `cart_id`. */
export function fetchCart(): Promise<CartPayload | null> {
  return api.fetchCart<CartPayload>();
}

export async function fetchProducts(): Promise<Product[] | null> {
  const data = await api.get<{ products: Product[] }>("/products", { limit: GRID_LIMIT });
  return data?.products ?? null;
}

export function fetchProduct(productId: string): Promise<ProductDetails | null> {
  return api.get<ProductDetails>(`/products/${encodeURIComponent(productId)}`);
}

/** `POST /api/cart/add` answers `{ ok, cart, checkout_url, cart_id }`; the extras are folded into the cart. */
export async function addToCart(productId: string, quantity = 1): Promise<CartPayload | null> {
  const data = await api.post<{
    cart: CartPayload | null;
    checkout_url?: string | null;
    cart_id?: string | null;
  }>("/cart/add", { product_id: productId, quantity });
  if (!data?.cart) return null;
  return { ...data.cart, checkout_url: data.checkout_url, cart_id: data.cart_id };
}

/** Binds the session to a cart that exists already — the storefront's `cart` cookie value
 * (the Shopware context token) works as-is. Null when the shop doesn't know the id. */
export function attachCart(cartId: string): Promise<CartPayload | null> {
  return api.post<CartPayload>("/cart/attach", { cart_id: cartId });
}

/** Grid catalog → shopping session (search + provenance) so chat can name visible products. */
export function syncCatalog(): Promise<{ ok: boolean; products: number } | null> {
  return api.post<{ ok: boolean; products: number }>("/session/sync-catalog", {});
}

export function fetchBrand(): Promise<Brand | null> {
  return api.get<Brand>("/brand");
}

export function fetchAuthStatus(): Promise<AuthStatus | null> {
  return api.get<AuthStatus>("/auth/status");
}

export function signOut(): Promise<AuthStatus | null> {
  return api.post<AuthStatus>("/auth/signout", {});
}

/**
 * Identity Linking, step one: the API answers `{ authorization_url }` for this session. The
 * browser then leaves for it as a top-level navigation; the OAuth callback lands back on
 * `WEB_APP_URL?signed_in=1`. The session id rides along as a query parameter too, because the
 * callback has no session header to correlate with.
 */
export async function fetchSignInUrl(sessionId: string): Promise<string | null> {
  const data = await api.get<{ authorization_url?: string | null }>("/auth/shopware/start", { session_id: sessionId });
  return data?.authorization_url ?? null;
}
