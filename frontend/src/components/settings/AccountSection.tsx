"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { ChangePasswordForm } from "./ChangePasswordForm";
import { GlobalSignoutButton } from "./GlobalSignoutButton";
import { DeleteAccountDialog } from "./DeleteAccountDialog";
import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";

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
 *
 * AccountSection reads `supabase.auth.getUser()` to fetch the current
 * user's email (passed to DeleteAccountDialog for the typed-email
 * safeguard). Renders a placeholder until the email is loaded.
 */
export function AccountSection() {
  const supabase = createClient();
  const [userEmail, setUserEmail] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void supabase.auth.getUser().then(({ data }) => {
      if (active) setUserEmail(data.user?.email ?? null);
    });
    return () => {
      active = false;
    };
  }, [supabase]);

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
          {userEmail ? (
            <DeleteAccountDialog userEmail={userEmail} />
          ) : (
            <p className="text-sm text-muted-foreground">Cargando…</p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
