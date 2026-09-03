// Copyright 2026 Shopify Inc.
// SPDX-License-Identifier: Apache-2.0

"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ActivityButton } from "web-shared/ActivityButton";
import type { Brand } from "@/lib/types";

const SIGN_IN_ERROR_MS = 5000;

/**
 * Identity Linking leaves the app: the button asks the host for the authorization URL and
 * the browser navigates there. While signed in, a small badge and a sign-out button show.
 */
function ShopSignIn({
  sessionId,
  signedIn,
  onSignIn,
  onSignOut,
}: {
  sessionId: string | null;
  signedIn: boolean;
  onSignIn: () => Promise<boolean>;
  onSignOut: () => void;
}) {
  const [phase, setPhase] = useState<"idle" | "busy" | "error">("idle");
  useEffect(() => {
    if (phase !== "error") return;
    const timer = window.setTimeout(() => setPhase("idle"), SIGN_IN_ERROR_MS);
    return () => window.clearTimeout(timer);
  }, [phase]);

  if (signedIn) {
    return (
      <span
        data-signed-in
        className="flex items-center gap-1.5 rounded-full bg-(--accent-soft) py-1 pl-3 pr-1.5 text-[13px] font-semibold text-(--ink)"
      >
        <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-emerald-600" />
        Signed in
        <button
          type="button"
          onClick={onSignOut}
          className="rounded-full px-1.5 py-0.5 text-[11px] font-medium text-(--ink-soft) hover:text-(--ink)"
        >
          Sign out
        </button>
      </span>
    );
  }
  return (
    <button
      type="button"
      disabled={!sessionId || phase === "busy"}
      title={phase === "error" ? "Sign-in isn't available right now. You can keep shopping as a guest." : undefined}
      onClick={async () => {
        setPhase("busy");
        const left = await onSignIn();
        // On success the page is navigating away; only the failure needs a state.
        if (!left) setPhase("error");
      }}
      className={`rounded-full bg-(--brand) px-3.5 py-1.5 text-[13px] font-semibold text-(--brand-contrast) transition hover:brightness-110 disabled:opacity-50 ${
        phase === "busy" ? "animate-pulse" : ""
      }`}
    >
      {phase === "error" ? "Sign-in unavailable" : phase === "busy" ? "Opening…" : "Sign in"}
    </button>
  );
}

export default function Header({
  brand,
  sessionId,
  signedIn,
  onSignIn,
  onSignOut,
  cartCount,
  onOpenCart,
  assistantOpen,
  onToggleAssistant,
  streaming,
  newMemoryCount,
  onOpenActivity,
}: {
  brand: Brand | null;
  sessionId: string | null;
  signedIn: boolean;
  onSignIn: () => Promise<boolean>;
  onSignOut: () => void;
  cartCount: number;
  onOpenCart: () => void;
  assistantOpen: boolean;
  onToggleAssistant: () => void;
  streaming: boolean;
  newMemoryCount: number;
  onOpenActivity: () => void;
}) {
  // Pulse the counter when the cart grows; it is the only visible cue for mid-turn agent adds.
  const previousCountRef = useRef(cartCount);
  const [pulsing, setPulsing] = useState(false);
  useEffect(() => {
    if (cartCount > previousCountRef.current) {
      setPulsing(true);
      const timer = window.setTimeout(() => setPulsing(false), 600);
      previousCountRef.current = cartCount;
      return () => window.clearTimeout(timer);
    }
    previousCountRef.current = cartCount;
  }, [cartCount]);

  return (
    <header className="flex items-center justify-between gap-3 border-b border-(--line) bg-(--card) px-5 py-3">
      <Link href="/" className="flex min-w-0 items-center gap-2.5">
        {brand?.logo_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={brand.logo_url} alt="" className="h-8 w-8 shrink-0 rounded-md object-contain" />
        ) : null}
        <span className="truncate text-lg font-extrabold tracking-tight text-(--ink)">
          {brand?.name ?? "Storefront"}
        </span>
        {brand?.slogan ? (
          <span className="hidden truncate text-[13px] text-(--ink-soft)/80 md:inline">{brand.slogan}</span>
        ) : null}
      </Link>
      <div className="flex shrink-0 items-center gap-2">
        <ShopSignIn sessionId={sessionId} signedIn={signedIn} onSignIn={onSignIn} onSignOut={onSignOut} />
        <ActivityButton streaming={streaming} newMemoryCount={newMemoryCount} onClick={onOpenActivity} />
        <button
          type="button"
          onClick={onOpenCart}
          aria-label={`Open cart, ${cartCount} item${cartCount === 1 ? "" : "s"}`}
          className="flex items-center gap-1.5 rounded-full border border-(--line) bg-(--card) px-3 py-1 text-[13px] font-semibold text-(--ink) transition hover:border-(--brand)"
        >
          Cart
          <span
            data-cart-target
            className={`rounded-full bg-(--accent-soft) px-1.5 py-0.5 text-[11px] font-bold text-(--ink) ${
              pulsing ? "ac-pop" : ""
            }`}
          >
            {cartCount}
          </span>
        </button>
        <button
          type="button"
          onClick={onToggleAssistant}
          aria-pressed={assistantOpen}
          className={`rounded-full border px-3 py-1 text-[13px] font-semibold transition ${
            assistantOpen
              ? "border-(--brand) bg-(--accent-soft) text-(--ink)"
              : "border-(--line) bg-(--card) text-(--ink) hover:border-(--brand)"
          }`}
        >
          Assistant
        </button>
      </div>
    </header>
  );
}
