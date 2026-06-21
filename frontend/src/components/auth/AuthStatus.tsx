"use client";

import { createClient } from "@/lib/supabase/client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";

/**
 * `scope` controls the Supabase `signOut({ scope })` argument:
 *   - `'local'` (DEFAULT, unchanged): revoke only this tab's session.
 *   - `'global'`: revoke every session in the project for this user.
 *
 * The header chip keeps `scope: 'local'` by default (existing UX).
 * Settings callers can pass `scope="global"` to opt into the
 * "sign out everywhere" behavior (REQ-AUTH-019 / REQ-AUTH-020).
 */
export interface AuthStatusProps {
  scope?: "local" | "global";
}

export function AuthStatus({ scope = "local" }: AuthStatusProps) {
  const supabase = createClient();
  const router = useRouter();
  const [email, setEmail] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // 1. Estado inicial: leer sesión actual
    supabase.auth.getSession().then(({ data: { session } }) => {
      setEmail(session?.user?.email ?? null);
      setLoading(false);
    });

    // 2. Escuchar cambios de auth en tiempo real
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event, session) => {
      setEmail(session?.user?.email ?? null);
      setLoading(false);
    });

    return () => subscription.unsubscribe();
  }, [supabase]);

  async function logout() {
    if (scope === "global") {
      await supabase.auth.signOut({ scope: "global" });
    } else {
      await supabase.auth.signOut();
    }
    router.push("/login");
    router.refresh();
  }

  if (loading) return null;

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
