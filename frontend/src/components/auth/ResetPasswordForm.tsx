"use client";

import { useRef } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { useTranslations } from "next-intl";
import { Loader2 } from "lucide-react";

import { createClient } from "@/lib/supabase/client";
import { resetPasswordSchema, type ResetPasswordValues } from "@/lib/validation/authSchemas";

/**
 * ResetPasswordForm — REQ-AUTH-004 / REQ-AUTH-005.
 *
 * Mounted inside `/reset-password`. Caller (the page) verifies the
 * Supabase recovery session is active before rendering; this form is
 * the new-password + confirm-password UI.
 *
 * On success: `supabase.auth.updateUser({ password })` then
 * `router.replace('/dashboard')`. On error: localized toast.
 *
 * Slice 5: migrated from `authCopy` to `useTranslations`.
 */
export function ResetPasswordForm() {
  const supabase = createClient();
  const router = useRouter();
  const t = useTranslations("Auth.resetPassword");
  const tValidation = useTranslations("Validation");
  const tToast = useTranslations("Auth.toast");
  const newPasswordRef = useRef<HTMLInputElement | null>(null);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting, isValid },
  } = useForm<ResetPasswordValues>({
    resolver: zodResolver(resetPasswordSchema),
    mode: "onChange",
    defaultValues: { password: "", confirmPassword: "" },
  });

  const { ref: passwordRHFRef, ...passwordRest } = register("password");
  const { ref: confirmRHFRef, ...confirmRest } = register("confirmPassword");

  async function onSubmit(values: ResetPasswordValues) {
    const { error } = await supabase.auth.updateUser({ password: values.password });

    if (error) {
      toast.error(tToast("networkError"));
      return;
    }

    toast.success(t("successToast"));
    reset();
    router.replace("/dashboard");
  }

  const passwordErrorKey = errors.password?.message;
  const confirmErrorKey = errors.confirmPassword?.message;
  const passwordError = passwordErrorKey
    ? tValidation(passwordErrorKey.replace(/^Validation\./, "") as never)
    : undefined;
  const confirmError = confirmErrorKey
    ? tValidation(confirmErrorKey.replace(/^Validation\./, "") as never)
    : undefined;

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      noValidate
      className="flex flex-col gap-4"
      aria-labelledby="reset-password-heading"
    >
      <header className="flex flex-col gap-1 text-center">
        <h1 id="reset-password-heading" className="font-display text-xl font-bold">
          {t("title")}
        </h1>
        <p className="text-sm text-muted-foreground">{t("subtitle")}</p>
      </header>

      <div className="flex flex-col gap-1.5" data-invalid={passwordError ? "" : undefined}>
        <label htmlFor="reset-password" className="text-sm font-medium">
          {t("newPasswordLabel")}
        </label>
        <input
          id="reset-password"
          type="password"
          autoComplete="new-password"
          aria-invalid={passwordError ? "true" : "false"}
          aria-describedby={passwordError ? "reset-password-error" : undefined}
          className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          {...passwordRest}
          ref={(el) => {
            passwordRHFRef(el);
            newPasswordRef.current = el;
          }}
        />
        {passwordError && (
          <p
            id="reset-password-error"
            role="alert"
            aria-live="polite"
            className="text-xs text-destructive"
          >
            {passwordError}
          </p>
        )}
      </div>

      <div className="flex flex-col gap-1.5" data-invalid={confirmError ? "" : undefined}>
        <label htmlFor="reset-confirm" className="text-sm font-medium">
          {t("confirmPasswordLabel")}
        </label>
        <input
          id="reset-confirm"
          type="password"
          autoComplete="new-password"
          aria-invalid={confirmError ? "true" : "false"}
          aria-describedby={confirmError ? "reset-confirm-error" : undefined}
          className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          {...confirmRest}
          ref={(el) => {
            confirmRHFRef(el);
          }}
        />
        {confirmError && (
          <p
            id="reset-confirm-error"
            role="alert"
            aria-live="polite"
            className="text-xs text-destructive"
          >
            {confirmError}
          </p>
        )}
      </div>

      <button
        type="submit"
        disabled={isSubmitting || !isValid}
        className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
      >
        {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
        {t("submit")}
      </button>
    </form>
  );
}