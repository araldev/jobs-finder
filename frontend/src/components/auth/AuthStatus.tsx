"use client";

import { createClient } from "@/lib/supabase/client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";

export function AuthStatus() {
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
    await supabase.auth.signOut();
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
