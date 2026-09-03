// Copyright 2026 Shopify Inc.
// SPDX-License-Identifier: Apache-2.0

"use client";

import { useCallback, useEffect, useState } from "react";

import { api, fetchAuthStatus, fetchSignInUrl, signOut as postSignOut } from "./api";

const STORAGE_KEY = "shopware-storefront-session";

export interface StoreSession {
  /** Null while the session is starting or after it failed. */
  sessionId: string | null;
  signedIn: boolean;
  /** Re-reads /api/auth/status; call after returning from Shopware sign-in. */
  refreshAuth: () => Promise<void>;
  /** Fetches the Identity Linking URL and leaves the page for it; false when the API refused. */
  signIn: () => Promise<boolean>;
  signOut: () => Promise<void>;
}

/**
 * Unlike the shared useSession, the session here survives page navigations:
 * Shopware sign-in leaves the app for Identity Linking and comes back, and the cart is
 * keyed to the session on the host. The id is kept in sessionStorage and revalidated
 * against /api/auth/status on mount; a dead or unknown id falls back to a fresh session.
 */
export function useStoreSession(): StoreSession {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [signedIn, setSignedIn] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const stored = window.sessionStorage.getItem(STORAGE_KEY);
      if (stored) {
        api.session = stored;
        const status = await fetchAuthStatus();
        if (status) {
          if (!cancelled) {
            setSessionId(stored);
            setSignedIn(status.signed_in);
          }
          return;
        }
      }
      api.session = null;
      const started = await api.startSession();
      if (cancelled) return;
      const fresh = started?.sessionId ?? null;
      if (fresh) {
        window.sessionStorage.setItem(STORAGE_KEY, fresh);
        api.session = fresh;
      }
      setSessionId(fresh);
      setSignedIn(false);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const refreshAuth = useCallback(async () => {
    const status = await fetchAuthStatus();
    if (status) setSignedIn(status.signed_in);
  }, []);

  const signIn = useCallback(async () => {
    if (!sessionId) return false;
    const url = await fetchSignInUrl(sessionId);
    if (!url) return false;
    // A top-level navigation, not a fetch: Shopware's OAuth page has to own the tab.
    window.location.assign(url);
    return true;
  }, [sessionId]);

  const signOut = useCallback(async () => {
    const status = await postSignOut();
    if (status) setSignedIn(status.signed_in);
  }, []);

  return { sessionId, signedIn, refreshAuth, signIn, signOut };
}
