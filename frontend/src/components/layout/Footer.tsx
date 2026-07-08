"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { Logo } from "./Logo";

/**
 * Site-wide footer. Renders the privacy-policy link and the
 * "Spanish only — English version coming soon" disclaimer while
 * the `/privacidad` page is still untranslated.
 *
 * Layout (desktop, md+):
 *   ┌────────────────────────────────────────────────────────────┐
 *   │ Logo + "Jobs Finder"   Privacy · Note · Copyright   Spacer │
 *   └────────────────────────────────────────────────────────────┘
 *
 * - Logo + name are vertically centered on the LEFT (the link wraps
 *   the Logo + the brand name as a single clickable unit that returns
 *   to the landing page). The brand name is intentionally not
 *   translated: "Jobs Finder" is a proper noun / brand name.
 * - The privacy link + the privacyNote + the copyright stay vertically
 *   stacked in the CENTER (preserves the v3 layout so users still see
 *   the disclaimer in the same visual breath as the privacy link).
 * - On mobile (sm), the layout stacks vertically: brand → privacy → note
 *   → copyright, each on its own row, all centered.
 *
 * Mounted per-page in `app/[locale]/{page,privacidad,jobs/[id]}/page.tsx`
 * (auth pages — login, signup, forgot/reset-password — intentionally
 * skip the footer to keep the auth flow focused).
 */
export function Footer() {
  const t = useTranslations("Footer");

  return (
    <footer className="border-t bg-card/30 px-6 py-6">
      <div className="flex flex-col items-center gap-3 text-center md:flex-row md:items-center md:justify-between md:text-left">
        {/* Left: Logo + brand name (vertically centered, links to landing) */}
        <Link
          href="/"
          className="flex items-center gap-2 text-foreground hover:opacity-80 transition-opacity"
          aria-label="Jobs Finder"
        >
          <Logo size="sm" />
          <span className="font-display text-base font-bold tracking-tight">
            Jobs Finder
          </span>
        </Link>

        {/* Center: privacy link + privacyNote + copyright (stacked, centered) */}
        <div className="flex flex-col items-center gap-1 text-center">
          <Link
            href="/privacidad"
            className="text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
          >
            {t("privacy")}
          </Link>
          <p className="text-xs text-muted-foreground">{t("privacyNote")}</p>
          <p className="text-xs text-muted-foreground">{t("copyright")}</p>
        </div>

        {/* Right: invisible spacer so the center column stays truly centered
            in the available width (Logo + name on the left, spacer on the
            right). Same width as the Logo block so justify-between keeps
            the center column dead-center on desktop. */}
        <div className="hidden md:block md:w-[140px]" aria-hidden="true" />
      </div>
    </footer>
  );
}
