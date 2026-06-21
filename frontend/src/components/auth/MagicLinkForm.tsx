"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { Mail } from "lucide-react";

import { createClient } from "@/lib/supabase/client";
import { authCopy } from "@/lib/authCopy";
import { magicLinkSchema, type MagicLinkValues } from "@/lib/validation/authSchemas";

/**
 * MagicLinkForm — REQ-AUTH-017.
 *
 * Passwordless OTP sign-in option mounted on `/login` (Feature E).
 * Calls `supabase.auth.signInWithOtp({ email, options: { emailRedirectTo } })`
 * with `emailRedirectTo = ${origin}/auth/callback?next=/dashboard` so the
 * existing callback's `?next=` validator (commit 2) drops the user on
 * `/dashboard` after the magic-link click.
 *
 * The form shares the email field with the surrounding login page
 * (the parent passes the email down via prop OR the user types in
 * this component's own field — the design supports both). For the
 * current implementation we use a separate field so the OTP button
 * is independent of the password login form.
 */
export interface MagicLinkFormProps {
  /** Pre-fill the email input from the parent's email field (optional). */
  initialEmail?: string;
}

export function MagicLinkForm({ initialEmail = "" }: MagicLinkFormProps) {
  const supabase = createClient();
  const [submitted, setSubmitted] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting, isValid },
  } = useForm<MagicLinkValues>({
    resolver: zodResolver(magicLinkSchema),
    mode: "onChange",
    defaultValues: { email: initialEmail },
  });

  async function onSubmit(values: MagicLinkValues) {
    const { error } = await supabase.auth.signInWithOtp({
      email: values.email,
      options: {
        emailRedirectTo: `${window.location.origin}/auth/callback?next=/dashboard`,
      },
    });

    if (error) {
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
      <div className="flex flex-col gap-3 text-center" data-testid="magic-link-success">
        <h2 className="font-display text-lg font-semibold">{authCopy.magicLink.successTitle}</h2>
        <p className="text-sm text-muted-foreground">{authCopy.magicLink.successDescription}</p>
      </div>
    );
  }

  const emailError = errors.email?.message;

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      noValidate
      className="flex flex-col gap-3"
      aria-labelledby="magic-link-heading"
    >
      <header className="flex flex-col gap-1">
        <h3 id="magic-link-heading" className="font-display text-sm font-semibold">
          {authCopy.magicLink.title}
        </h3>
        <p className="text-xs text-muted-foreground">{authCopy.magicLink.subtitle}</p>
      </header>

      <div className="flex flex-col gap-1.5" data-invalid={emailError ? "" : undefined}>
        <label htmlFor="magic-link-email" className="sr-only">
          Tu correo electrónico
        </label>
        <input
          id="magic-link-email"
          type="email"
          autoComplete="email"
          aria-invalid={emailError ? "true" : "false"}
          aria-describedby={emailError ? "magic-link-error" : undefined}
          placeholder="tu@email.com"
          className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          {...register("email")}
        />
        {emailError && (
          <p
            id="magic-link-error"
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
        className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-border bg-background px-4 py-2 text-sm font-medium transition-colors hover:bg-muted disabled:opacity-50"
      >
        <Mail className="h-4 w-4" data-icon="inline-start" aria-hidden="true" />
        {authCopy.magicLink.submit}
      </button>
    </form>
  );
}
