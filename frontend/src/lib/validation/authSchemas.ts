import { z } from "zod";

/**
 * zod validation schemas for the 5 auth flows introduced by
 * `auth-flows` (REQ-AUTH-005 + per-form length/match rules).
 *
 * Error messages are now translation KEYS (e.g. `Validation.emailRequired`)
 * rather than literal strings. The form components that render these
 * errors resolve the key via `useTranslations('Validation')` so a single
 * schema serves both locales.
 *
 * Reusable in any of these patterns:
 *   1. `safeParse` from a form submit handler (raw `useState` flow).
 *   2. `@hookform/resolvers/zod` resolver when wired through
 *      `react-hook-form` (commit 2 onward).
 *   3. Ad-hoc server-action validation.
 *
 * Why KEYS instead of literals: a future move to additional locales is
 * purely additive (one more `messages/<locale>.json` file) — no schema
 * edits. The trade-off is that the form must call `t(error.message)`
 * before rendering, instead of dropping the message string into JSX
 * directly. Each form's test suite updates accordingly.
 */

const emailSchema = z
  .string({ message: "Validation.emailRequired" })
  .trim()
  .min(1, { message: "Validation.emailRequired" })
  .email({ message: "Validation.emailInvalid" });

const passwordSchema = z
  .string({ message: "Validation.passwordRequired" })
  .min(6, { message: "Validation.passwordMinLength" });

// ─── A. forgot-password ───────────────────────────────────────────────────
export const forgotPasswordSchema = z.object({
  email: emailSchema,
});
export type ForgotPasswordValues = z.infer<typeof forgotPasswordSchema>;

// ─── A. reset-password ───────────────────────────────────────────────────
export const resetPasswordSchema = z
  .object({
    password: passwordSchema,
    confirmPassword: passwordSchema,
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: "Validation.passwordsDoNotMatch",
    path: ["confirmPassword"],
  });
export type ResetPasswordValues = z.infer<typeof resetPasswordSchema>;

// ─── D. change-password (logged-in) ──────────────────────────────────────
export const changePasswordSchema = z
  .object({
    currentPassword: z
      .string({ message: "Validation.passwordRequired" })
      .min(1, { message: "Validation.passwordRequired" }),
    newPassword: passwordSchema,
    confirmPassword: passwordSchema,
  })
  .refine((data) => data.newPassword === data.confirmPassword, {
    message: "Validation.passwordsDoNotMatch",
    path: ["confirmPassword"],
  })
  .refine((data) => data.newPassword !== data.currentPassword, {
    message: "Validation.passwordMustDiffer",
    path: ["newPassword"],
  });
export type ChangePasswordValues = z.infer<typeof changePasswordSchema>;

// ─── E. magic-link (login OTP) ───────────────────────────────────────────
export const magicLinkSchema = z.object({
  email: emailSchema,
});
export type MagicLinkValues = z.infer<typeof magicLinkSchema>;

// ─── C. delete-account confirm (typed-email safeguard) ───────────────────
export const deleteAccountConfirmSchema = z.object({
  confirmEmail: emailSchema,
});
export type DeleteAccountConfirmValues = z.infer<typeof deleteAccountConfirmSchema>;

/**
 * Helper for components that need to know whether two emails match
 * case-insensitively and trimmed (the typed-email safeguard UX). The
 * zod schema validates the email format; this helper validates the
 * *match* against the user's actual `user.email` value.
 */
export function emailsMatchCaseInsensitive(a: string, b: string): boolean {
  return a.trim().toLowerCase() === b.trim().toLowerCase();
}