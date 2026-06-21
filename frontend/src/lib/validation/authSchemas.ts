import { z } from "zod";
import { authCopy } from "@/lib/authCopy";

/**
 * zod validation schemas for the 5 auth flows introduced by
 * `auth-flows` (REQ-AUTH-005 + per-form length/match rules).
 *
 * Each schema's error messages are pulled from `authCopy.ts` so a
 * future i18n migration is mechanical (key → translation) and no
 * Spanish literal lives inside a component.
 *
 * Reusable in any of these patterns:
 *   1. `safeParse` from a form submit handler (raw `useState` flow).
 *   2. `@hookform/resolvers/zod` resolver when wired through
 *      `react-hook-form` (commit 2 onward).
 *   3. Ad-hoc server-action validation.
 */

const emailSchema = z
  .string({ message: authCopy.validation.emailRequired })
  .trim()
  .min(1, { message: authCopy.validation.emailRequired })
  .email({ message: authCopy.validation.emailInvalid });

const passwordSchema = z
  .string({ message: authCopy.validation.passwordRequired })
  .min(6, { message: authCopy.validation.passwordMinLength });

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
    message: authCopy.validation.passwordsDoNotMatch,
    path: ["confirmPassword"],
  });
export type ResetPasswordValues = z.infer<typeof resetPasswordSchema>;

// ─── D. change-password (logged-in) ──────────────────────────────────────
export const changePasswordSchema = z
  .object({
    currentPassword: z
      .string({ message: authCopy.validation.passwordRequired })
      .min(1, { message: authCopy.validation.passwordRequired }),
    newPassword: passwordSchema,
    confirmPassword: passwordSchema,
  })
  .refine((data) => data.newPassword === data.confirmPassword, {
    message: authCopy.validation.passwordsDoNotMatch,
    path: ["confirmPassword"],
  })
  .refine((data) => data.newPassword !== data.currentPassword, {
    message: authCopy.validation.passwordMustDiffer,
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
