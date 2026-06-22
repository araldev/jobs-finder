"use client";

import Link from "next/link";
import Image from "next/image";
import { createClient } from "@/lib/supabase/client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useTranslations } from "next-intl";
import { ArrowLeft } from "lucide-react";

export default function SignupPage() {
  const supabase = createClient();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const tAuth = useTranslations("Auth.signup");
  const tCommon = useTranslations("Common");

  async function signup(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    const form = new FormData(e.currentTarget);
    const email = form.get("email") as string;
    const password = form.get("password") as string;

    const { error: authError } = await supabase.auth.signUp({
      email,
      password,
      options: {
        emailRedirectTo: `${location.origin}/auth/callback`,
      },
    });

    setLoading(false);

    if (authError) {
      setError(authError.message);
      return;
    }

    router.push("/?welcome=true");
    router.refresh();
  }

  async function signupWithGoogle() {
    const { error: authError } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: {
        redirectTo: `${location.origin}/auth/callback`,
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
          {tCommon("backToHome")}
        </Link>
      </div>

      <div className="mx-auto mt-8 max-w-sm space-y-6 px-4">
        <div className="space-y-2 text-center">
          <Link href="/" className="inline-flex items-center gap-2">
            <Image src="/favicon.svg" alt="Jobs Finder" width={36} height={36} className="h-9 w-9" />
            <span className="font-display text-xl font-bold">Jobs Finder</span>
          </Link>
          <h1 className="mt-4 text-2xl font-display font-bold">{tAuth("title")}</h1>
          <p className="text-sm text-muted-foreground">{tAuth("subtitle")}</p>
        </div>

        <form onSubmit={signup} className="space-y-4">
          <div className="space-y-2">
            <label htmlFor="email" className="text-sm font-medium">
              {tAuth("emailLabel")}
            </label>
            <input
              id="email"
              name="email"
              type="email"
              placeholder={tAuth("emailPlaceholder")}
              required
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
            />
          </div>

          <div className="space-y-2">
            <label htmlFor="password" className="text-sm font-medium">
              {tAuth("passwordLabel")}
            </label>
            <input
              id="password"
              name="password"
              type="password"
              placeholder="••••••••"
              required
              minLength={6}
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
            {loading ? tAuth("loading") : tAuth("submit")}
          </button>
        </form>

        <div className="relative">
          <div className="absolute inset-0 flex items-center">
            <span className="w-full border-t border-border" />
          </div>
          <div className="relative flex justify-center text-xs uppercase">
            <span className="bg-background px-2 text-muted-foreground">
              {tAuth("orContinueWith")}
            </span>
          </div>
        </div>

        <button
          onClick={signupWithGoogle}
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
          {tAuth("continueWithGoogle")}
        </button>

        <p className="text-center text-sm text-muted-foreground">
          {tAuth("haveAccount")}{" "}
          <Link href="/login" className="text-foreground underline underline-offset-4 hover:no-underline">
            {tAuth("signIn")}
          </Link>
        </p>
      </div>
    </div>
  );
}
