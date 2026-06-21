"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import Link from "next/link";
import { Loader2 } from "lucide-react";

import { createClient } from "@/lib/supabase/client";
import { authCopy } from "@/lib/authCopy";
import { forgotPasswordSchema, type ForgotPasswordValues } from "@/lib/validation/authSchemas";

/**
 * ForgotPasswordForm — REQ-AUTH-001 / REQ-AUTH-002 / REQ-AUTH-003.
 *
 * Renders an email input + submit. On valid submit, calls
 * `supabase.auth.resetPasswordForEmail(email, { redirectTo })` with a
 * `redirectTo` ending in `/auth/callback?next=/reset-password` (so the
 * callback's existing `?next=` validator — see
 * `app/auth/callback/route.ts` — drops the user on `/reset-password`).
 *
 * No user-enumeration disclosure (REQ-AUTH-003): the success state is
 * byte-identical for known and unknown emails. The mock returns a
 * canned `{ data, error: null }` for every call; production Supabase
 * also returns `{ data: { user: null }, error: null }` for unknown
 * emails.
 */
export function ForgotPasswordForm() {
  const supabase = createClient();
  const [submitted, setSubmitted] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting, isValid },
  } = useForm<ForgotPasswordValues>({
    resolver: zodResolver(forgotPasswordSchema),
    mode: "onChange",
  });

  async function onSubmit(values: ForgotPasswordValues) {
    const { error } = await supabase.auth.resetPasswordForEmail(values.email, {
      redirectTo: `${window.location.origin}/auth/callback?next=/reset-password`,
    });

    if (error) {
      // REQ-AUTH-025: surface failures via sonner. We do NOT leak the
      // error class (`AuthApiError` vs `AuthRetryableFetchError`) to
      // the user — a single Spanish message covers both.
      const isRateLimit =
        (error as { status?: number }).status === 429 ||
        /rate/i.test(error.message);
      toast.error(isRateLimit ? authCopy.toast.rateLimit : authCopy.toast.networkError);
      return;
    }

    setSubmitted(true);
  }

  if (submitted) {
    return (
      <div className="flex flex-col gap-3 text-center" data-testid="forgot-success">
        <h2 className="font-display text-lg font-semibold">{authCopy.forgot.successTitle}</h2>
        <p className="text-sm text-muted-foreground">{authCopy.forgot.successDescription}</p>
      </div>
    );
  }

  const emailError = errors.email?.message;

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      noValidate
      className="flex flex-col gap-4"
      aria-labelledby="forgot-password-heading"
    >
      <header className="flex flex-col gap-1 text-center">
        <h1 id="forgot-password-heading" className="font-display text-xl font-bold">
          {authCopy.forgot.title}
        </h1>
        <p className="text-sm text-muted-foreground">{authCopy.forgot.subtitle}</p>
      </header>

      <div className="flex flex-col gap-1.5" data-invalid={emailError ? "" : undefined}>
        <label htmlFor="forgot-email" className="text-sm font-medium">
          {authCopy.forgot.emailLabel}
        </label>
        <input
          id="forgot-email"
          type="email"
          autoComplete="email"
          aria-invalid={emailError ? "true" : "false"}
          aria-describedby={emailError ? "forgot-email-error" : undefined}
          className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          {...register("email")}
        />
        {emailError && (
          <p
            id="forgot-email-error"
            role="alert"
            aria-live="polite"
            className="text-xs text-destructive"
          >
            {emailError}
          </p>
        )}
      </div>

      <button
        type="submit"
        disabled={isSubmitting || !isValid}
        className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
      >
        {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
        {authCopy.forgot.submit}
      </button>

      <Link
        href="/login"
        className="text-center text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
      >
        {authCopy.forgot.backToLogin}
      </Link>
    </form>
  );
}
