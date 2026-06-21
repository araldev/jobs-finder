"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { MailCheck, RefreshCw, X } from "lucide-react";

import { createClient } from "@/lib/supabase/client";
import { authCopy } from "@/lib/authCopy";

/**
 * EmailVerificationBanner — REQ-AUTH-006 / REQ-AUTH-007 / REQ-AUTH-008.
 *
 * V2 non-gating reminder: surfaces a banner inside `(app)/layout.tsx`
 * when the signed-in user's email is still unverified. Does NOT block
 * routes — the user can use every (app) feature while the banner is
 * visible.
 *
 * Data source: `supabase.auth.getUser()` (NOT `getSession()` —
 * `getUser()` validates the JWT against GoTrue and returns fresh
 * `email_confirmed_at` data; `getSession()` returns the stale JWT
 * payload). Also subscribes to `onAuthStateChange` so a click on the
 * verification link updates the banner without a page reload
 * (REQ-AUTH-007-1).
 *
 * Dismiss flag: `sessionStorage["jf-verify-banner-dismissed"]` — set
 * on click of "Descartar", read on mount. The flag is session-scoped
 * (NOT localStorage) so a new browser session re-shows the banner
 * if the email is still unverified (REQ-AUTH-004 — V2 spec).
 */
const DISMISS_KEY = "jf-verify-banner-dismissed";

interface UserSnapshot {
  email: string;
  emailConfirmedAt: string | null;
}

export function EmailVerificationBanner() {
  const supabase = createClient();
  const [user, setUser] = useState<UserSnapshot | null>(null);
  const [dismissTick, setDismissTick] = useState(0);

  useEffect(() => {
    let active = true;

    async function loadUser() {
      const { data } = await supabase.auth.getUser();
      if (!active) return;
      const u = data.user;
      setUser(
        u
          ? {
              email: u.email ?? "",
              emailConfirmedAt: u.email_confirmed_at ?? null,
            }
          : null,
      );
    }

    void loadUser();

    // Subscribe to auth state changes — when the user clicks the
    // verification link, Supabase fires SIGNED_IN with a fresh JWT,
    // and getUser() returns the updated email_confirmed_at.
    const { data: { subscription } } = supabase.auth.onAuthStateChange(() => {
      void loadUser();
    });

    return () => {
      active = false;
      subscription.unsubscribe();
    };
  }, [supabase]);

  async function handleResend() {
    if (!user?.email) return;
    const { error } = await supabase.auth.resend({ type: "signup", email: user.email });
    if (error) {
      toast.error(authCopy.banner.resendErrorToast);
      return;
    }
    toast.success(authCopy.banner.resendToast);
  }

  function handleDismiss() {
    sessionStorage.setItem(DISMISS_KEY, "1");
    // Re-read the storage flag on next render via the tick counter.
    setDismissTick((t) => t + 1);
  }

  // Read the dismiss flag on every render so toggling sessionStorage
  // outside the component (or via this component's dismiss button)
  // is reflected without waiting for an effect re-run.
  const dismissed =
    typeof sessionStorage !== "undefined"
      ? sessionStorage.getItem(DISMISS_KEY) === "1"
      : false;
  // Touch the tick so React tracks the dependency (avoid lint warnings
  // + ensure the component re-renders after handleDismiss).
  void dismissTick;

  // No user yet → render nothing.
  if (user === null) return null;

  // Verified user — no banner.
  if (user.emailConfirmedAt) return null;

  // Dismissed this session — no banner.
  if (dismissed) return null;

  return (
    <div
      role="alert"
      data-testid="email-verification-banner"
      className="mb-4 flex flex-col gap-3 rounded-xl border border-warning/40 bg-warning/10 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
    >
      <div className="flex items-start gap-3">
        <MailCheck className="mt-0.5 h-5 w-5 text-warning" aria-hidden="true" />
        <div className="flex flex-col gap-0.5">
          <p className="text-sm font-medium">{authCopy.banner.title}</p>
          <p className="text-xs text-muted-foreground">{authCopy.banner.description}</p>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={handleResend}
          className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-medium transition-colors hover:bg-muted"
        >
          <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
          {authCopy.banner.resend}
        </button>
        <button
          type="button"
          onClick={handleDismiss}
          aria-label={authCopy.banner.dismiss}
          className="inline-flex items-center justify-center rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}
