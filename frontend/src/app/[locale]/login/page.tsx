"use client";

import Link from "next/link";
import Image from "next/image";
import { createClient } from "@/lib/supabase/client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { ArrowLeft } from "lucide-react";

import { MagicLinkForm } from "@/components/auth/MagicLinkForm";

export default function LoginPage() {
  const supabase = createClient();
  const router = useRouter();
  const t = useTranslations("Auth.login");
  const tCommon = useTranslations("Common");
  const locale = useLocale();
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  // Controlled email state (REQ-MAINT-017, ADR-006): the previous implementation
  // used emailRef.current?.value at render time, which is null on the first
  // render (refs are set AFTER first commit). Lifting to useState lets the parent
  // re-render MagicLinkForm with the typed email as `initialEmail` and forces a
  // remount via the `key` prop on every keystroke (RHF reads defaultValues only
  // on mount).
  const [email, setEmail] = useState<string>("");

  async function login(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    const form = new FormData(e.currentTarget);
    const email = form.get("email") as string;
    const password = form.get("password") as string;

    const { error: authError } = await supabase.auth.signInWithPassword({
      email,
      password,
    });

    setLoading(false);

    if (authError) {
      setError(authError.message);
      return;
    }

    router.push("/dashboard");
    router.refresh();
  }

  async function loginWithGoogle() {
    // Use the explicit `NEXT_PUBLIC_SITE_URL` env var when set (so the
    // redirectTo is consistent regardless of the access hostname —
    // critical for OAuth: Supabase rejects codes when the callback
    // URL doesn't match the project's allowlisted URLs, and
    // `0.0.0.0:3000` is NOT in the default allowlist). Falls back to
    // `location.origin` (the browser's current origin) so dev still
    // works without the env var. The check `=== 'localhost'` is a
    // safety net: if the env var is empty, force localhost.
    const siteUrl =
      process.env.NEXT_PUBLIC_SITE_URL?.trim() ||
      (location.hostname === "0.0.0.0" || location.hostname === "[::1]"
        ? "http://localhost:3000"
        : location.origin);
    const { error: authError } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: {
        redirectTo: `${siteUrl}/auth/callback`,
        queryParams: {
          prompt: "select_account",
        },
      },
    });
    if (authError) setError(authError.message);
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Back to home */}
      <div className="p-4">
<Link
            href="/"
            className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            <ArrowLeft className="h-4 w-4" />
            {tCommon("back")}
          </Link>
      </div>

      <div className="mx-auto mt-8 max-w-sm space-y-6 px-4">
        <div className="space-y-2 text-center">
          <Link href="/" className="inline-flex items-center gap-2">
            <Image src="/favicon.svg" alt="Jobs Finder" width={36} height={36} className="h-9 w-9" />
            <span className="font-display text-xl font-bold">Jobs Finder</span>
          </Link>
          <h1 className="mt-4 text-2xl font-display font-bold">{t("title")}</h1>
          <p className="text-sm text-muted-foreground">
            {t("subtitle")}
          </p>
        </div>

        <form onSubmit={login} className="space-y-4">
          <div className="space-y-2">
            <label htmlFor="email" className="text-sm font-medium">
              Email
            </label>
            <input
              id="email"
              name="email"
              type="email"
              placeholder="tu@email.com"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
            />
          </div>

          <div className="space-y-2">
            <div className="flex items-baseline justify-between">
              <label htmlFor="password" className="text-sm font-medium">
                Contraseña
              </label>
              <Link
                href="/forgot-password"
                className="text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
              >
                ¿Olvidaste tu contraseña?
              </Link>
            </div>
            <input
              id="password"
              name="password"
              type="password"
              placeholder="••••••••"
              required
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
            />
          </div>

          {error && (
            <p className="text-sm text-destructive">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-foreground px-4 py-2 text-sm font-medium text-background transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {loading ? "Entrando..." : "Entrar"}
          </button>
        </form>

        {/* Feature E — magic-link / OTP login (REQ-AUTH-017).
            The form below the password login lets the user request a
            one-time link by email. Reuses the same email field via
            the `initialEmail` prop if pre-filled; otherwise it's
            independent.

            REQ-MAINT-017 + ADR-006: `key={email}` forces MagicLinkForm
            to remount on every email change so react-hook-form re-reads
            `defaultValues: { email: initialEmail }` on mount. Without
            the key, RHF only reads defaultValues on the FIRST mount and
            the OTP email input would stay empty when the user types in
            the password form then switches to OTP. */}
        <div className="border-t border-border pt-4">
          <MagicLinkForm key={email} initialEmail={email} />
        </div>

        <div className="relative">
          <div className="absolute inset-0 flex items-center">
            <span className="w-full border-t border-border" />
          </div>
          <div className="relative flex justify-center text-xs uppercase">
            <span className="bg-background px-2 text-muted-foreground">
              o continuá con
            </span>
          </div>
        </div>

        <button
          onClick={loginWithGoogle}
          className="flex w-full items-center justify-center gap-3 rounded-lg border border-border bg-background px-4 py-2.5 text-sm font-medium transition-colors hover:bg-muted"
        >
          <svg className="h-5 w-5" viewBox="0 0 24 24">
            <path
              d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
              fill="#4285F4"
            />
            <path
              d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
              fill="#34A853"
            />
            <path
              d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
              fill="#FBBC05"
            />
            <path
              d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
              fill="#EA4335"
            />
          </svg>
          Continuar con Google
        </button>

        <p className="text-center text-sm text-muted-foreground">
          ¿No tenés cuenta?{" "}
          <Link href="/signup" className="text-foreground underline underline-offset-4 hover:no-underline">
            Registrate
          </Link>
        </p>
      </div>
    </div>
  );
}
