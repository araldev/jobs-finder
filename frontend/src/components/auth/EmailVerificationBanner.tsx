"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { useTranslations } from "next-intl";
import { MailCheck, RefreshCw, X } from "lucide-react";

import { createClient } from "@/lib/supabase/client";

/**
 * EmailVerificationBanner — REQ-AUTH-006 / REQ-AUTH-007 / REQ-AUTH-008.
 *
 * V2 non-gating reminder: surfaces a banner inside `(app)/layout.tsx`
 * when the signed-in user's email is still unverified. Does NOT block
 * routes — the user can use every (app) feature while the banner is
 * visible.
 *
 * Slice 5: migrated from `authCopy` to `useTranslations`.
 */
const DISMISS_KEY = "jf-verify-banner-dismissed";

interface UserSnapshot {
  email: string;
  emailConfirmedAt: string | null;
}

export function EmailVerificationBanner() {
  const supabase = createClient();
  const t = useTranslations("Auth.emailVerification");
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

  if (user === null) return null;
  if (user.emailConfirmedAt) return null;
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