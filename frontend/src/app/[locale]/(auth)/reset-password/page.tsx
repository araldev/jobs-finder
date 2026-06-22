import { createClient } from "@/lib/supabase/server";
import { ResetPasswordForm } from "@/components/auth/ResetPasswordForm";
import Link from "next/link";
import { getTranslations } from "next-intl/server";

/**
 * /reset-password page — REQ-AUTH-004.
 *
 * Verifies the Supabase recovery session is active before rendering the
 * form. If no session (link expired or never existed), shows the
 * "invalid-link" state with a "Volver a solicitar" link to
 * `/forgot-password` (REQ-AUTH-004-1).
 *
 * Server component — `supabase.auth.getSession()` runs on the server
 * during SSR so the initial render already shows the right branch
 * (no flash of the wrong state).
 */
export default async function ResetPasswordPage() {
  const supabase = await createClient();
  const t = await getTranslations("Auth.resetPassword");
  const { data: { session } } = await supabase.auth.getSession();

  if (!session) {
    return (
      <div className="flex flex-col gap-4 text-center" data-testid="reset-invalid-link">
        <h1 className="font-display text-xl font-bold">{t("invalidLinkTitle")}</h1>
        <p className="text-sm text-muted-foreground">{t("invalidLinkDescription")}</p>
        <Link
          href="/forgot-password"
          className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
        >
          {t("resendLink")}
        </Link>
      </div>
    );
  }

  return <ResetPasswordForm />;
}
