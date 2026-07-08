"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Search,
  Briefcase,
  Settings,
  FileText,
  type LucideIcon,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { ThemeToggle } from "./ThemeToggle";
import { LanguageSwitcher } from "./LanguageSwitcher";
import { AuthStatus } from "@/components/auth/AuthStatus";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { cn } from "@/lib/utils";

/**
 * Page metadata for the header. The order matters for the
 * "longest-prefix wins" lookup below — more specific paths
 * must appear before their parents.
 *
 * Labels are translation KEYS (e.g. `Navigation.dashboard.label`) — the
 * component calls `t(key)` at render time. Description + screen-reader
 * labels are translated through `Navigation.<route>.description` and
 * `Navigation.<route>.screenReader` respectively.
 */
const ROUTE_META: Array<{
  prefixes: string[];
  translationKey: "dashboard" | "search" | "favorites" | "jobDetail" | "settings";
  icon: LucideIcon;
  /** Tailwind gradient stop colors for the icon bubble. */
  gradient: string;
}> = [
  {
    prefixes: ["/dashboard"],
    translationKey: "dashboard",
    icon: LayoutDashboard,
    gradient: "from-primary/20 to-primary/5",
  },
  {
    prefixes: ["/search"],
    translationKey: "search",
    icon: Search,
    gradient: "from-secondary/20 to-secondary/5",
  },
  {
    prefixes: ["/favorites"],
    translationKey: "favorites",
    icon: Briefcase,
    gradient: "from-emerald-500/20 to-emerald-500/5",
  },
  {
    prefixes: ["/jobs/"],
    translationKey: "jobDetail",
    icon: Briefcase,
    gradient: "from-primary/20 to-primary/5",
  },
  {
    prefixes: ["/settings"],
    translationKey: "settings",
    icon: Settings,
    gradient: "from-muted to-muted/30",
  },
] as const;

function resolveRoute(pathname: string) {
  for (const route of ROUTE_META) {
    if (route.prefixes.some((p) => pathname === p || pathname.startsWith(p))) {
      return route;
    }
  }
  return null;
}

export function Header() {
  const pathname = usePathname();
  const t = useTranslations("Navigation");
  const { data: user } = useCurrentUser();
  const route = resolveRoute(pathname);

  const label = route ? t(`${route.translationKey}.label`) : t("fallback.label");
  const description = route
    ? t(`${route.translationKey}.description`)
    : t("fallback.description");
  const Icon = route?.icon ?? Briefcase;
  const gradient = route?.gradient ?? "from-primary/20 to-primary/5";

  return (
    <header className="flex h-20 items-center justify-between border-b bg-card/30 px-6 backdrop-blur-sm">
      <div className="flex items-center gap-4">
        <div
          className={cn(
            "flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br shadow-sm ring-1 ring-inset ring-white/10",
            gradient,
          )}
        >
          <Icon className="h-5 w-5 text-foreground" />
        </div>
        <div className="flex flex-col">
          <h1 className="font-display text-xl font-bold leading-tight tracking-tight text-foreground">
            {label}
          </h1>
          <p className="text-xs text-muted-foreground">{description}</p>
        </div>
      </div>
      <div className="flex items-center gap-3">
        {user && (
          <Link href="/adapt-cv">
            <Button size="sm" className="gap-2">
              <FileText className="h-4 w-4" />
              {t("adaptCv.label")}
            </Button>
          </Link>
        )}
        <AuthStatus />
        <Separator orientation="vertical" className="h-6" />
        <LanguageSwitcher />
        <ThemeToggle />
      </div>
    </header>
  );
}