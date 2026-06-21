"use client";

import { useRef } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";

import { createClient } from "@/lib/supabase/client";
import { authCopy } from "@/lib/authCopy";
import { changePasswordSchema, type ChangePasswordValues } from "@/lib/validation/authSchemas";

/**
 * ChangePasswordForm — REQ-AUTH-015 / REQ-AUTH-016.
 *
 * Three password fields (current, new, confirm). Submit disabled until:
 *   - new ≥ 6 chars (matches the signup rule)
 *   - new === confirm
 *   - current is non-empty
 *   - new !== current (defense: don't rotate to the same password)
 *
 * On submit: `supabase.auth.updateUser({ password })`. Success →
 * toast.success + clear all three inputs. Failure with
 * "Invalid login credentials" → toast.error("Contraseña actual
 * incorrecta") + focus the current-password field.
 */
export function ChangePasswordForm() {
  const supabase = createClient();
  const currentPasswordRef = useRef<HTMLInputElement | null>(null);

  const {
    register,
    handleSubmit,
    reset,
    setFocus,
    formState: { errors, isSubmitting, isValid },
  } = useForm<ChangePasswordValues>({
    resolver: zodResolver(changePasswordSchema),
    mode: "onChange",
    defaultValues: { currentPassword: "", newPassword: "", confirmPassword: "" },
  });

  const { ref: currentRHFRef, ...currentRest } = register("currentPassword");
  const { ref: newRHFRef, ...newRest } = register("newPassword");
  const { ref: confirmRHFRef, ...confirmRest } = register("confirmPassword");

  async function onSubmit(values: ChangePasswordValues) {
    const { error } = await supabase.auth.updateUser({ password: values.newPassword });

    if (error) {
      // REQ-AUTH-016-2: wrong current password surfaces a specific
      // Spanish message and refocuses the current-password field.
      if (/invalid login credentials/i.test(error.message)) {
        toast.error(authCopy.change.wrongCurrentToast);
        setFocus("currentPassword");
        return;
      }
      // Other failures: generic Spanish toast.
      toast.error(authCopy.toast.networkError);
      setFocus("currentPassword");
      return;
    }

    toast.success(authCopy.change.successToast);
    reset();
  }

  const currentError = errors.currentPassword?.message;
  const newError = errors.newPassword?.message;
  const confirmError = errors.confirmPassword?.message;

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      noValidate
      className="flex flex-col gap-4"
      aria-labelledby="change-password-heading"
    >
      <h3 id="change-password-heading" className="font-display text-base font-semibold">
        {authCopy.change.title}
      </h3>
      <p className="text-sm text-muted-foreground">{authCopy.change.subtitle}</p>

      <div className="flex flex-col gap-1.5" data-invalid={currentError ? "" : undefined}>
        <label htmlFor="change-current" className="text-sm font-medium">
          {authCopy.change.currentPasswordLabel}
        </label>
        <input
          id="change-current"
          type="password"
          autoComplete="current-password"
          aria-invalid={currentError ? "true" : "false"}
          aria-describedby={currentError ? "change-current-error" : undefined}
          className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          {...currentRest}
          ref={(el) => {
            currentRHFRef(el);
            currentPasswordRef.current = el;
          }}
        />
        {currentError && (
          <p id="change-current-error" role="alert" aria-live="polite" className="text-xs text-destructive">
            {currentError}
          </p>
        )}
      </div>

      <div className="flex flex-col gap-1.5" data-invalid={newError ? "" : undefined}>
        <label htmlFor="change-new" className="text-sm font-medium">
          {authCopy.change.newPasswordLabel}
        </label>
        <input
          id="change-new"
          type="password"
          autoComplete="new-password"
          aria-invalid={newError ? "true" : "false"}
          aria-describedby={newError ? "change-new-error" : undefined}
          className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          {...newRest}
          ref={(el) => {
            newRHFRef(el);
          }}
        />
        {newError && (
          <p id="change-new-error" role="alert" aria-live="polite" className="text-xs text-destructive">
            {newError}
          </p>
        )}
      </div>

      <div className="flex flex-col gap-1.5" data-invalid={confirmError ? "" : undefined}>
        <label htmlFor="change-confirm" className="text-sm font-medium">
          {authCopy.change.confirmPasswordLabel}
        </label>
        <input
          id="change-confirm"
          type="password"
          autoComplete="new-password"
          aria-invalid={confirmError ? "true" : "false"}
          aria-describedby={confirmError ? "change-confirm-error" : undefined}
          className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          {...confirmRest}
          ref={(el) => {
            confirmRHFRef(el);
          }}
        />
        {confirmError && (
          <p id="change-confirm-error" role="alert" aria-live="polite" className="text-xs text-destructive">
            {confirmError}
          </p>
        )}
      </div>

      <button
        type="submit"
        disabled={isSubmitting || !isValid}
        className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50 sm:w-auto"
      >
        {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
        {authCopy.change.submit}
      </button>
    </form>
  );
}
