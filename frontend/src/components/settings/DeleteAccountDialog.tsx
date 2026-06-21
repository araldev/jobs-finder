"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { AlertTriangle, Trash2 } from "lucide-react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";

import { createClient } from "@/lib/supabase/client";
import { authCopy } from "@/lib/authCopy";
import {
  deleteAccountConfirmSchema,
  emailsMatchCaseInsensitive,
  type DeleteAccountConfirmValues,
} from "@/lib/validation/authSchemas";
import { cleanupJobsFinderLocalStorage } from "@/lib/auth/cleanupJobsFinderLocalStorage";

/**
 * DeleteAccountDialog — REQ-AUTH-011 / REQ-AUTH-012 / REQ-AUTH-013.
 *
 * Destructive account-deletion flow.
 *
 * Safety layering (defense in depth):
 *   1. UI: typed-email safeguard (user must type their exact email,
 *      case-insensitive trimmed, to enable the confirm button).
 *   2. RPC: `supabase.rpc('delete_current_user')` runs server-side in
 *      Postgres with `SECURITY DEFINER` + an `auth.uid() IS NULL`
 *      guard (the real safety — the UI is a soft UX gate).
 *   3. Side effects in order on success:
 *      a. `cleanupJobsFinderLocalStorage()` — sweep `jobs-finder-*`
 *         keys so the next sign-in doesn't see stale favorites.
 *      b. `supabase.auth.signOut()` — invalidate the JWT.
 *      c. `router.push('/')` — redirect to the landing page.
 *
 * On RPC failure: Spanish toast + dialog stays open (user can retry
 * or cancel). REQ-AUTH-025.
 */
export interface DeleteAccountDialogProps {
  /** The current user's email. Used for the typed-email safeguard. */
  userEmail: string;
}

export function DeleteAccountDialog({ userEmail }: DeleteAccountDialogProps) {
  const supabase = createClient();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isValid },
  } = useForm<DeleteAccountConfirmValues>({
    resolver: zodResolver(deleteAccountConfirmSchema),
    mode: "onChange",
    defaultValues: { confirmEmail: "" },
  });

  // Watch the input so the confirm button enables/disables live as
  // the user types (case-insensitive trimmed match against the user's
  // real email — REQ-AUTH-011-2).
  const typedEmail = watch("confirmEmail") ?? "";
  const match = emailsMatchCaseInsensitive(typedEmail, userEmail);

  async function handleConfirm() {
    // Use the typed-email watch directly (the form's onSubmit may not
    // fire if the form is using a zod schema with onChange mode —
    // the typed-match check is the real safeguard here).
    if (!isValid || !match) return;

    setBusy(true);

    // Step 1: localStorage cleanup (run BEFORE the RPC + signOut so
    // any in-flight session can't write a new key after the sweep).
    cleanupJobsFinderLocalStorage();

    // Step 2: the actual server-side deletion via Postgres RPC.
    // The RPC's SECURITY DEFINER body handles the auth.users delete +
    // cascade. No service-role key in the browser.
    const { error } = await supabase.rpc("delete_current_user");

    if (error) {
      toast.error(authCopy.delete.errorToast);
      setBusy(false);
      // Dialog stays open — user can retry or cancel.
      return;
    }

    // Step 3: sign out (invalidates the JWT the browser holds).
    await supabase.auth.signOut();

    toast.success(authCopy.delete.successToast);
    setBusy(false);
    setOpen(false);
    router.push("/");
  }

  // onSubmit wrapper (keeps the <form> semantic + handles Enter key).
  async function onSubmit(_values: DeleteAccountConfirmValues) {
    await handleConfirm();
  }

  const typedError = errors.confirmEmail?.message;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <AlertTriangle className="h-4 w-4 text-destructive" aria-hidden="true" />
        <h3 className="font-display text-base font-semibold text-destructive">
          {authCopy.delete.title}
        </h3>
      </div>
      <p className="text-sm text-muted-foreground">{authCopy.delete.subtitle}</p>
      <p className="text-xs text-muted-foreground">{authCopy.delete.destructiveHelp}</p>

      <AlertDialog open={open} onOpenChange={setOpen}>
        <AlertDialogTrigger asChild>
          <Button variant="destructive" size="sm" className="self-start" data-testid="delete-account-trigger">
            <Trash2 className="h-4 w-4" data-icon="inline-start" aria-hidden="true" />
            {authCopy.delete.triggerLabel}
          </Button>
        </AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{authCopy.delete.confirmTitle}</AlertDialogTitle>
            <AlertDialogDescription>
              {authCopy.delete.confirmDescription}
            </AlertDialogDescription>
          </AlertDialogHeader>

          <form
            id="delete-account-form"
            onSubmit={handleSubmit(onSubmit)}
            noValidate
            className="flex flex-col gap-2"
            aria-labelledby="delete-account-confirm-label"
          >
            <label
              id="delete-account-confirm-label"
              htmlFor="delete-account-confirm"
              className="text-sm font-medium"
            >
              {authCopy.delete.confirmEmailLabel}
            </label>
            <input
              id="delete-account-confirm"
              type="email"
              autoComplete="email"
              placeholder={authCopy.delete.confirmPlaceholder}
              aria-invalid={typedError || (typedEmail && !match) ? "true" : "false"}
              aria-describedby="delete-account-confirm-hint"
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              data-testid="delete-account-confirm-input"
              {...register("confirmEmail")}
            />
            <p
              id="delete-account-confirm-hint"
              role="alert"
              aria-live="polite"
              className="text-xs text-destructive"
            >
              {typedError ?? (typedEmail && !match ? authCopy.validation.deleteEmailMismatch : "")}
            </p>
          </form>

          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}>
              {authCopy.delete.confirmCancel}
            </AlertDialogCancel>
            <AlertDialogAction
              type="button"
              onClick={(e) => {
                // AlertDialogAction's default behavior is to close the
                // dialog. We only want to close on SUCCESS (in
                // handleConfirm). Prevent the default close so the
                // dialog stays open on RPC errors.
                e.preventDefault();
                void handleConfirm();
              }}
              disabled={busy || !isValid || !match}
              aria-disabled={busy || !isValid || !match}
              data-testid="delete-account-confirm"
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {authCopy.delete.confirmSubmit}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
