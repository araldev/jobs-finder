"use client";

import { usePathname } from "next/navigation";
import { ThemeToggle } from "./ThemeToggle";
import { AuthStatus } from "@/components/auth/AuthStatus";

const routeLabels: Record<string, string> = {
  "/": "Dashboard",
  "/jobs": "Jobs",
  "/search": "Search",
  "/settings": "Settings",
};

export function Header() {
  const pathname = usePathname();
  const label = routeLabels[pathname] ?? "JobsBoard";

  return (
    <header className="flex h-14 items-center justify-between border-b px-6">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <span className="font-medium text-foreground">{label}</span>
      </div>
      <div className="flex items-center gap-4">
        <AuthStatus />
        <ThemeToggle />
      </div>
    </header>
  );
}
