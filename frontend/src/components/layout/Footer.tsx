"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";

/**
 * Site-wide footer. Renders the privacy-policy link and the
 * "Spanish only — English version coming soon" disclaimer while
 * the `/privacidad` page is still untranslated.
 *
 * Mounted in the root layout (under the (app) routes' content) so
 * it appears on every page. The privacy note intentionally sits
 * directly below the privacy link so users see the disclaimer in
 * the same visual breath as the link they were about to follow.
 */
export function Footer() {
  const t = useTranslations("Footer");

  return (
    <footer className="border-t bg-card/30 px-6 py-6">
      <div className="flex flex-col items-center gap-2 text-center">
        <div className="flex items-center gap-4">
          <Link
            href="/privacidad"
            className="text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
          >
            {t("privacy")}
          </Link>
        </div>
        <p className="text-xs text-muted-foreground">{t("privacyNote")}</p>
        <p className="text-xs text-muted-foreground">{t("copyright")}</p>
      </div>
    </footer>
  );
}