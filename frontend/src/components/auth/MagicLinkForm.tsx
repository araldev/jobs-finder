"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { useTranslations } from "next-intl";
import { Mail } from "lucide-react";

import { createClient } from "@/lib/supabase/client";
import { magicLinkSchema, type MagicLinkValues } from "@/lib/validation/authSchemas";

/**
 * MagicLinkForm — REQ-AUTH-017.
 *
 * Passwordless OTP sign-in option mounted on `/login` (Feature E).
 * Calls `supabase.auth.signInWithOtp({ email, options: { emailRedirectTo } })`
 * with `emailRedirectTo = ${origin}/auth/callback?next=/dashboard`.
 *
 * Slice 5: migrated from `authCopy` to `useTranslations`. The "tu@email.com"
 * placeholder is now a translation key (`Auth.magicLink.placeholder` would
 * be added in a follow-up if we want to localize it).
 */
export interface MagicLinkFormProps {
  /** Pre-fill the email input from the parent's email field (optional). */
  initialEmail?: string;
}

export function MagicLinkForm({ initialEmail = "" }: MagicLinkFormProps) {
  const supabase = createClient();
  const t = useTranslations("Auth.magicLink");
  const tValidation = useTranslations("Validation");
  const tToast = useTranslations("Auth.toast");
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
      toast.error(isRateLimit ? tToast("rateLimit") : tToast("networkError"));
      return;
    }

    setSubmitted(true);
  }

  if (submitted) {
    return (
      <div className="flex flex-col gap-3 text-center" data-testid="magic-link-success">
        <h2 className="font-display text-lg font-semibold">{t("successTitle")}</h2>
        <p className="text-sm text-muted-foreground">{t("successDescription")}</p>
      </div>
    );
  }

  const emailErrorKey = errors.email?.message;
  const emailError = emailErrorKey
    ? tValidation(emailErrorKey.replace(/^Validation\./, "") as never)
    : undefined;

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      noValidate
      className="flex flex-col gap-3"
      aria-labelledby="magic-link-heading"
    >
      <header className="flex flex-col gap-1">
        <h3 id="magic-link-heading" className="font-display text-sm font-semibold">
          {t("title")}
        </h3>
        <p className="text-xs text-muted-foreground">{t("subtitle")}</p>
      </header>

      <div className="flex flex-col gap-1.5" data-invalid={emailError ? "" : undefined}>
        <label htmlFor="magic-link-email" className="sr-only">
          Email
        </label>
        <input
          id="magic-link-email"
          type="email"
          autoComplete="email"
          aria-invalid={emailError ? "true" : "false"}
          aria-describedby={emailError ? "magic-link-error" : undefined}
          placeholder="you@example.com"
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
        {t("submit")}
      </button>
    </form>
  );
}