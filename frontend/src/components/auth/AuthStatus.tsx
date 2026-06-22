"use client";

import { createClient } from "@/lib/supabase/client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { useCurrentUser } from "@/hooks/useCurrentUser";

/**
 * `scope` controls the Supabase `signOut({ scope })` argument:
 *   - `'local'` (DEFAULT, unchanged): revoke only this tab's session.
 *   - `'global'`: revoke every session in the project for this user.
 *
 * The header chip keeps `scope: 'local'` by default (existing UX).
 * Settings callers can pass `scope="global"` to opt into the
 * "sign out everywhere" behavior (REQ-AUTH-019 / REQ-AUTH-020).
 *
 * REQ-PDPRSC-004 refactor (commit 5): auth state is read from the
 * shared `useCurrentUser` hook instead of calling
 * `supabase.auth.getSession()` directly + subscribing to
 * `onAuthStateChange`. The hook owns the subscription lifecycle
 * (mounted on hook mount, invalidated on every auth event, cleaned
 * up on unmount). One `/auth/v1/user` fetch per 5min cache window,
 * shared with `EmailVerificationBanner`.
 */
export interface AuthStatusProps {
  scope?: "local" | "global";
}

export function AuthStatus({ scope = "local" }: AuthStatusProps) {
  const supabase = createClient();
  const router = useRouter();
  const { data: user, isLoading } = useCurrentUser();

  const email = user?.email ?? null;

  async function logout() {
    if (scope === "global") {
      await supabase.auth.signOut({ scope: "global" });
    } else {
      await supabase.auth.signOut();
    }
    router.push("/login");
    router.refresh();
  }

  if (isLoading) return null;

  if (email) {
    return (
      <div className="flex items-center gap-3">
        <Link
          href="/settings"
          className="text-sm text-muted-foreground transition-colors hover:text-foreground"
        >
          {email}
        </Link>
        <Button variant="outline" size="sm" onClick={logout}>
          Cerrar sesión
        </Button>
      </div>
    );
  }

  return (
    <Link
      href="/login"
      className="rounded-lg bg-foreground px-3 py-1.5 text-xs font-medium text-background transition-opacity hover:opacity-90"
    >
      Iniciar sesión
    </Link>
  );
}