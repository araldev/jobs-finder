"use client";

import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { LogOut, Info } from "lucide-react";

import { createClient } from "@/lib/supabase/client";
import { authCopy } from "@/lib/authCopy";

/**
 * GlobalSignoutButton — REQ-AUTH-019.
 *
 * "Cerrar sesión en todos los dispositivos" — calls
 * `supabase.auth.signOut({ scope: 'global' })` then `router.push('/')`.
 *
 * UI contract:
 *   - Single destructive-styled button.
 *   - Muted helper text documents the ~1h token-lifetime behavior
 *     (REQ-AUTH-019-2) so users don't think it's a bug when their
 *     other tabs keep working for up to an hour.
 *   - No confirmation dialog — signOut is non-destructive (the user
 *     can sign back in immediately with the same password) and a
 *     second click is cheaper than a second dialog.
 */
export function GlobalSignoutButton() {
  const supabase = createClient();
  const router = useRouter();

  async function handleSignOut() {
    const { error } = await supabase.auth.signOut({ scope: "global" });

    if (error) {
      toast.error(authCopy.globalSignOut.errorToast);
      return;
    }

    router.push("/");
  }

  return (
    <div className="flex flex-col gap-3">
      <h3 className="font-display text-base font-semibold">
        {authCopy.globalSignOut.confirmTitle}
      </h3>
      <div className="flex items-start gap-2 text-xs text-muted-foreground">
        <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        <p>{authCopy.globalSignOut.tooltip}</p>
      </div>
      <div>
        <button
          type="button"
          onClick={handleSignOut}
          className="inline-flex items-center gap-2 rounded-lg bg-destructive px-4 py-2 text-sm font-medium text-destructive-foreground transition-opacity hover:opacity-90"
        >
          <LogOut className="h-4 w-4" data-icon="inline-start" aria-hidden="true" />
          {authCopy.globalSignOut.triggerLabel}
        </button>
      </div>
    </div>
  );
}
