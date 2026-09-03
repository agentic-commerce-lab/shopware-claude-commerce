// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

import { AgentApi } from "web-shared";
import type {
  AlertsResponse,
  ChangeActionResponse,
  ChangesResponse,
  ChangeStatus,
  DashboardResponse,
  HealthResponse,
  ListingDetailResponse,
  ListingsResponse,
  OrdersResponse,
  OverviewResponse,
} from "./types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8005";

/** The shared client over the merchant host; every route below lives under `/api/merchant`. */
export const api = new AgentApi(API_URL, "/api/merchant");

export const UNREACHABLE =
  "Couldn't reach the Shopware merchant API on port 8005. Start it with " +
  "`uvicorn merchant.api.main:app --port 8005` and try again.";

const ORDERS_LIMIT = "20";

/** Public; the page shows its `error` while the host has no Shopware credentials and no session can start. */
export function fetchHealth(): Promise<HealthResponse | null> {
  return api.get<HealthResponse>("/health");
}

export function fetchOverview(): Promise<OverviewResponse | null> {
  return api.get<OverviewResponse>("/overview");
}

/** The "This week" row: null until the host exposes `/dashboard`, and the page falls back to the snapshot. */
export function fetchDashboard(): Promise<DashboardResponse | null> {
  return api.get<DashboardResponse>("/dashboard");
}

export function fetchListings(query?: string): Promise<ListingsResponse | null> {
  return api.get<ListingsResponse>("/listings", query ? { query } : undefined);
}

export function fetchListingDetail(listingId: string): Promise<ListingDetailResponse | null> {
  return api.get<ListingDetailResponse>(`/listings/${encodeURIComponent(listingId)}`);
}

export function fetchAlerts(): Promise<AlertsResponse | null> {
  return api.get<AlertsResponse>("/alerts");
}

export function fetchOrders(): Promise<OrdersResponse | null> {
  return api.get<OrdersResponse>("/orders", { limit: ORDERS_LIMIT });
}

export function fetchChanges(status: ChangeStatus | "all"): Promise<ChangesResponse | null> {
  return api.get<ChangesResponse>("/changes", { status });
}

export type ChangeAction = "apply" | "discard";

/**
 * Approve or dismiss through the same gate the assistant's own tools use. Unlike the shared
 * `actOnChange`, the whole answer comes back so a held change can show the gate's `reason`.
 * Null when the request itself failed.
 */
export function actOnChange(changeId: string, action: ChangeAction): Promise<ChangeActionResponse | null> {
  return api.post<ChangeActionResponse>(`/changes/${encodeURIComponent(changeId)}/${action}`);
}
