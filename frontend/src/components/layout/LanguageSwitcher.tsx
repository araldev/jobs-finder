"use client";

import { useLocale, useTranslations } from "next-intl";
import { usePathname, useRouter } from "next/navigation";
import { Languages, Check } from "lucide-react";
import { motion, useReducedMotion } from "framer-motion";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { routing, LOCALE_LABELS, type Locale } from "@/i18n/routing";

/**
 * Re-implementation of the strip-prefix helper for client-side use.
 * Identical to the one in `@/lib/supabase/middleware.ts` but kept local
 * so the LanguageSwitcher doesn't need to import from the middleware
 * (which is server-only conceptually). Tests assert identical behavior.
 */
function stripLocalePrefix(path: string): string {
  for (const l of routing.locales) {
    if (path === `/${l}`) return "/";
    if (path.startsWith(`/${l}/`)) return path.slice(l.length + 1);
  }
  return path;
}

interface LanguageSwitcherProps {
  /** True when mounted in the footer (text + icon variant) vs the header (icon-only). */
  inFooter?: boolean;
}

/**
 * Bilingual locale switcher — writes the `NEXT_LOCALE` cookie, mirrors
 * the choice in `localStorage` for instant client-side reads, navigates
 * to the locale-correct path, and calls `router.refresh()` so the RSC
 * tree (including `<html lang>`) re-renders (design D9).
 *
 * Mounted in the Header (icon-only `h-9 w-9`) for protected `(app)` routes
 * and in the Footer (text + icon) for public routes that don't have the
 * AppShell — see REQ-I18N-007 / design D11.
 *
 * Cookie attributes:
 *   - `path=/`         : available to every route
 *   - `max-age=...`    : 1 year, so the user's choice persists across sessions
 *   - `SameSite=Lax`   : required for the OAuth `redirectTo` flow which
 *                        crosses origins after the callback (D9 elaboration)
 */
export function LanguageSwitcher({ inFooter = false }: LanguageSwitcherProps) {
  const t = useTranslations("Common");
  const locale = useLocale() as Locale;
  const router = useRouter();
  const pathname = usePathname();
  const reducedMotion = useReducedMotion();

  function switchTo(target: Locale) {
    document.cookie = `NEXT_LOCALE=${target}; path=/; max-age=31536000; SameSite=Lax`;
    try {
      localStorage.setItem("NEXT_LOCALE", target);
    } catch {
      // localStorage may throw in private mode / SSR mocks — ignore.
    }
    const stripped = stripLocalePrefix(pathname);
    const nextPath =
      target === routing.defaultLocale ? stripped : `/${target}${stripped}`;
    router.push(nextPath);
    router.refresh();
  }

  const trigger = inFooter ? (
    <DropdownMenu.Trigger className="inline-flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground transition-colors">
      <Languages className="h-3.5 w-3.5" />
      {t("switcher.label")}
    </DropdownMenu.Trigger>
  ) : (
    <DropdownMenu.Trigger
      aria-label={t("switcher.label")}
      aria-haspopup="menu"
      className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-border bg-background hover:bg-muted transition-colors"
    >
      <Languages className="h-4 w-4" />
    </DropdownMenu.Trigger>
  );

  return (
    <DropdownMenu.Root>
      {trigger}
      <DropdownMenu.Portal>
        <DropdownMenu.Content align="end" sideOffset={8} asChild>
          <motion.div
            initial={reducedMotion ? { opacity: 0 } : { opacity: 0, scale: 0.95 }}
            animate={reducedMotion ? { opacity: 1 } : { opacity: 1, scale: 1 }}
            transition={
              reducedMotion
                ? { duration: 0.15 }
                : { type: "spring", bounce: 0.1, duration: 0.15 }
            }
            className="z-50 min-w-[10rem] overflow-hidden rounded-xl border border-border bg-popover text-popover-foreground shadow-md"
          >
            <DropdownMenu.RadioGroup
              value={locale}
              onValueChange={(v) => switchTo(v as Locale)}
            >
              {routing.locales.map((l) => (
                <DropdownMenu.RadioItem
                  key={l}
                  value={l}
                  className="flex cursor-pointer items-center justify-between px-3 py-2 text-sm outline-none data-[highlighted]:bg-muted"
                >
                  <span>{LOCALE_LABELS[l]}</span>
                  {locale === l && <Check className="h-4 w-4 text-primary" />}
                </DropdownMenu.RadioItem>
              ))}
            </DropdownMenu.RadioGroup>
          </motion.div>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}