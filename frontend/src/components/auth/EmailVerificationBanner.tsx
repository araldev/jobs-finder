"use client";

import { useState } from "react";
import { toast } from "sonner";
import { useTranslations } from "next-intl";
import { MailCheck, RefreshCw, X } from "lucide-react";

import { useCurrentUser } from "@/hooks/useCurrentUser";
import { createClient } from "@/lib/supabase/client";

/**
 * EmailVerificationBanner — REQ-AUTH-006 / REQ-AUTH-007 / REQ-AUTH-008.
 *
 * V2 non-gating reminder: surfaces a banner inside `(app)/layout.tsx`
 * when the signed-in user's email is still unverified. Does NOT block
 * routes — the user can use every (app) feature while the banner is
 * visible.
 *
 * REQ-PDPRSC-004 refactor (commit 5): the banner no longer calls
 * `supabase.auth.getUser()` directly on mount. Auth state lives in
 * the shared React Query cache via `useCurrentUser()` — the same
 * hook `AuthStatus` consumes. One `/auth/v1/user` fetch per cache
 * window (5min staleTime), shared across both consumers.
 *
 * The `supabase.auth.onAuthStateChange` subscription is now handled
 * by the hook itself (registered on mount, invalidated on every
 * auth event), so the banner does not register its own subscriber
 * anymore.
 */
const DISMISS_KEY = "jf-verify-banner-dismissed";

interface UserSnapshot {
  email: string;
  emailConfirmedAt: string | null;
}

function buildSnapshot(
  user:
    | {
        email?: string | null;
        email_confirmed_at?: string | null;
      }
    | null
    | undefined,
): UserSnapshot | null {
  if (!user) return null;
  return {
    email: user.email ?? "",
    emailConfirmedAt: user.email_confirmed_at ?? null,
  };
}

export function EmailVerificationBanner() {
  const { data: user } = useCurrentUser();
  const t = useTranslations("Auth.emailVerification");
  const [dismissTick, setDismissTick] = useState(0);

  const snapshot = buildSnapshot(user);

  async function handleResend() {
    if (!snapshot?.email) return;
    const supabase = createClient();
    const { error } = await supabase.auth.resend({
      type: "signup",
      email: snapshot.email,
    });
    if (error) {
      toast.error(t("resendErrorToast"));
      return;
    }
    toast.success(t("resendToast"));
  }

  function handleDismiss() {
    sessionStorage.setItem(DISMISS_KEY, "1");
    setDismissTick((tick) => tick + 1);
  }

  const dismissed =
    typeof sessionStorage !== "undefined"
      ? sessionStorage.getItem(DISMISS_KEY) === "1"
      : false;
  void dismissTick;

  if (snapshot === null) return null;
  if (snapshot.emailConfirmedAt) return null;
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
          <p className="text-sm font-medium">{t("title")}</p>
          <p className="text-xs text-muted-foreground">{t("description")}</p>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={handleResend}
          className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-medium transition-colors hover:bg-muted"
        >
          <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
          {t("resend")}
        </button>
        <button
          type="button"
          onClick={handleDismiss}
          aria-label={t("dismiss")}
          className="inline-flex items-center justify-center rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}