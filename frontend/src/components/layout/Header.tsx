"use client";

import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Search,
  Briefcase,
  Settings,
  type LucideIcon,
} from "lucide-react";
import { ThemeToggle } from "./ThemeToggle";
import { AuthStatus } from "@/components/auth/AuthStatus";
import { cn } from "@/lib/utils";

/**
 * Page metadata for the header. The order matters for the
 * "longest-prefix wins" lookup below — more specific paths
 * must appear before their parents.
 */
const ROUTE_META: Array<{
  prefixes: string[];
  label: string;
  description: string;
  icon: LucideIcon;
  /** Tailwind gradient stop colors for the icon bubble. */
  gradient: string;
}> = [
  {
    prefixes: ["/dashboard"],
    label: "Dashboard",
    description: "Overview of your job listings",
    icon: LayoutDashboard,
    gradient: "from-primary/20 to-primary/5",
  },
  {
    prefixes: ["/search"],
    label: "Search",
    description: "Find jobs by keyword, location, or source",
    icon: Search,
    gradient: "from-secondary/20 to-secondary/5",
  },
  {
    prefixes: ["/favorites"],
    label: "Favorites",
    description: "Jobs you saved for later",
    icon: Briefcase,
    gradient: "from-emerald-500/20 to-emerald-500/5",
  },
  {
    prefixes: ["/jobs/"],
    label: "Job Detail",
    description: "Full posting information",
    icon: Briefcase,
    gradient: "from-primary/20 to-primary/5",
  },
  {
    prefixes: ["/settings"],
    label: "Settings",
    description: "Platform configuration and preferences",
    icon: Settings,
    gradient: "from-muted to-muted/30",
  },
] as const;

const FALLBACK = {
  label: "Jobs Finder",
  description: "Smart job discovery across LinkedIn, Indeed, and InfoJobs",
  icon: Briefcase,
  gradient: "from-primary/20 to-primary/5",
} as const;

function resolveRoute(pathname: string) {
  for (const route of ROUTE_META) {
    if (route.prefixes.some((p) => pathname === p || pathname.startsWith(p))) {
      return route;
    }
  }
  return FALLBACK;
}

export function Header() {
  const pathname = usePathname();
  const { label, description, icon: Icon, gradient } = resolveRoute(pathname);

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
        <AuthStatus />
        <ThemeToggle />
      </div>
    </header>
  );
}
