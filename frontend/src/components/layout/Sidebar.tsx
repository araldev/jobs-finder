"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Briefcase,
  Search,
  Settings,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { cn } from "@/lib/utils";
import { Logo } from "./Logo";

const navItems = [
  { href: "/dashboard", key: "dashboard", icon: LayoutDashboard },
  { href: "/search", key: "search", icon: Search },
  { href: "/favorites", key: "favorites", icon: Briefcase },
  { href: "/settings", key: "settings", icon: Settings },
] as const;

type NavKey = (typeof navItems)[number]["key"];

export function Sidebar() {
  const pathname = usePathname();
  const t = useTranslations("Navigation");

  return (
    <aside className="flex w-64 flex-col border-r bg-card">
      {/* Logo — vuelve a la landing page de marketing */}
      <div className="flex h-14 items-center gap-3 border-b px-6">
        <Link href="/" className="flex items-center gap-3">
          <Logo size="md" />
          <span className="font-display text-lg font-semibold tracking-tight">
            Jobs Finder
          </span>
        </Link>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 px-3 py-4" aria-label={t("dashboard.label")}>
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = pathname.startsWith(item.href);

          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
              )}
              aria-current={isActive ? "page" : undefined}
            >
              <Icon className="h-4 w-4" aria-hidden="true" />
              <span>{t(`${item.key}.label`)}</span>
              {isActive && (
                <span className="sr-only">{t(`${item.key}.screenReader` as never)}</span>
              )}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="border-t px-6 py-3">
        <p className="text-xs text-muted-foreground">v0.1.0</p>
      </div>
    </aside>
  );
}