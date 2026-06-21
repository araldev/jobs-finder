import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { ChangePasswordForm } from "./ChangePasswordForm";
import { GlobalSignoutButton } from "./GlobalSignoutButton";
import { DeleteAccountDialog } from "./DeleteAccountDialog";
import { authCopy } from "@/lib/authCopy";

/**
 * AccountSection — REQ-AUTH-013 / REQ-AUTH-014.
 *
 * The 4th card on `/settings`. Composes three sub-sections, separated
 * by `<Separator />`:
 *   1. `<ChangePasswordForm />` — logged-in password rotation (D).
 *   2. `<GlobalSignoutButton />` — sign out everywhere (F).
 *   3. `<DeleteAccountDialog />` — destructive (C), wrapped in a
 *      `border border-destructive/40 rounded-xl p-6` sub-card so it
 *      is visually distinct (REQ-AUTH-013).
 *
 * The destructive sub-card is the LAST element so a user reading
 * top-to-bottom encounters the safe controls first.
 */
export function AccountSection() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="font-display text-lg">Cuenta</CardTitle>
        <CardDescription>
          Cambiá tu contraseña, cerrá sesión en otros dispositivos o eliminá tu cuenta.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        <ChangePasswordForm />
        <Separator />
        <GlobalSignoutButton />
        <Separator />
        <div
          className="rounded-xl border border-destructive/40 p-6"
          data-testid="delete-account-destructive-card"
        >
          <DeleteAccountDialog />
        </div>
      </CardContent>
    </Card>
  );
}
