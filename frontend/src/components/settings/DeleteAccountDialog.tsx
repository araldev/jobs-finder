"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { useTranslations } from "next-intl";
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
import {
  deleteAccountConfirmSchema,
  emailsMatchCaseInsensitive,
  type DeleteAccountConfirmValues,
} from "@/lib/validation/authSchemas";
import { cleanupJobsFinderLocalStorage } from "@/lib/auth/cleanupJobsFinderLocalStorage";

/**
 * DeleteAccountDialog — REQ-AUTH-011 / REQ-AUTH-012 / REQ-AUTH-013.
 *
 * Slice 5: migrated from `authCopy` to `useTranslations`.
 */
export interface DeleteAccountDialogProps {
  /** The current user's email. Used for the typed-email safeguard. */
  userEmail: string;
}

export function DeleteAccountDialog({ userEmail }: DeleteAccountDialogProps) {
  const supabase = createClient();
  const router = useRouter();
  const t = useTranslations("Auth.deleteAccount");
  const tValidation = useTranslations("Validation");
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

  const typedEmail = watch("confirmEmail") ?? "";
  const match = emailsMatchCaseInsensitive(typedEmail, userEmail);

  async function handleConfirm() {
    if (!isValid || !match) return;

    setBusy(true);

    // CRITICAL: RPC must run BEFORE localStorage cleanup (REQ-AUTH-012).
    const { error } = await supabase.rpc("delete_current_user");

    if (error) {
      toast.error(t("errorToast"));
      setBusy(false);
      return;
    }

    cleanupJobsFinderLocalStorage();
    await supabase.auth.signOut();

    toast.success(t("successToast"));
    setBusy(false);
    setOpen(false);
    router.push("/");
  }

  async function onSubmit(_values: DeleteAccountConfirmValues) {
    await handleConfirm();
  }

  const typedErrorKey = errors.confirmEmail?.message;
  const typedError = typedErrorKey
    ? tValidation(typedErrorKey.replace(/^Validation\./, "") as never)
    : undefined;
  const matchError =
    typedEmail && !match ? tValidation("deleteEmailMismatch" as never) : "";

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <AlertTriangle className="h-4 w-4 text-destructive" aria-hidden="true" />
        <h3 className="font-display text-base font-semibold text-destructive">
          {t("title")}
        </h3>
      </div>
      <p className="text-sm text-muted-foreground">{t("subtitle")}</p>
      <p className="text-xs text-muted-foreground">{t("destructiveHelp")}</p>

      <AlertDialog open={open} onOpenChange={setOpen}>
        <AlertDialogTrigger asChild>
          <Button variant="destructive" size="sm" className="self-start" data-testid="delete-account-trigger">
            <Trash2 className="h-4 w-4" data-icon="inline-start" aria-hidden="true" />
            {t("triggerLabel")}
          </Button>
        </AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("confirmTitle")}</AlertDialogTitle>
            <AlertDialogDescription>
              {t("confirmDescription")}
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
              {t("confirmEmailLabel")}
            </label>
            <input
              id="delete-account-confirm"
              type="email"
              autoComplete="email"
              placeholder={t("confirmPlaceholder")}
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
              {typedError ?? matchError}
            </p>
          </form>

          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}>
              {t("confirmCancel")}
            </AlertDialogCancel>
            <AlertDialogAction
              type="button"
              onClick={(e) => {
                e.preventDefault();
                void handleConfirm();
              }}
              disabled={busy || !isValid || !match}
              aria-disabled={busy || !isValid || !match}
              data-testid="delete-account-confirm"
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {t("confirmSubmit")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}