"use client";

/**
 * DeleteAccountDialog — REQ-AUTH-011 / REQ-AUTH-012 / REQ-AUTH-013.
 *
 * Full implementation lands in commit 5 of `auth-flows` (T-AUTH-010).
 * This file is created NOW so AccountSection can compose it as the
 * destructive sub-card (REQ-AUTH-013-1) without a follow-up refactor.
 *
 * For commit 4 the stub renders the destructive-styled card shell so
 * AccountSection's structural assertions pass; the
 * typed-email-safeguard form + RPC call + localStorage cleanup land
 * in commit 5 with their own tests.
 */
export function DeleteAccountDialog() {
  return (
    <div className="flex flex-col gap-3">
      <h3 className="font-display text-base font-semibold text-destructive">
        Eliminar cuenta
      </h3>
      <p className="text-sm text-muted-foreground">
        Esta acción es permanente y no se puede deshacer.
      </p>
      {/* Full form lands in commit 5 */}
      <div data-testid="delete-account-stub" aria-hidden="true" />
    </div>
  );
}
