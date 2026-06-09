"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { CircleAlert, CircleCheck, CircleDashed } from "lucide-react";
import { cn } from "@/lib/utils";

type HealthState = "loading" | "ok" | "degraded" | "down";

const POLL_INTERVAL_MS = 30_000;

async function fetchHealth(signal: AbortSignal): Promise<HealthState> {
  try {
    const res = await fetch("/api/health", { signal, cache: "no-store" });
    if (res.status === 200) return "ok";
    if (res.status === 503) return "degraded";
    return "down";
  } catch (cause) {
    if (cause instanceof Error && cause.name === "AbortError") return "loading";
    return "down";
  }
}

const STORAGE_KEY = "jobs-finder:onboarding-seen";

/**
 * Top app bar. Sticky, glass-styled, contains the brand mark on the
 * left and a backend health indicator on the right. Listens for the
 * Ctrl+Shift+R shortcut to reset the onboarding overlay for QA.
 */
export function Topbar(): React.ReactElement {
  const [health, setHealth] = useState<HealthState>("loading");

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    const tick = async () => {
      const next = await fetchHealth(controller.signal);
      if (!cancelled) setHealth(next);
    };

    void tick();
    const interval = setInterval(tick, POLL_INTERVAL_MS);

    const resetOnboarding = (event: KeyboardEvent) => {
      if (event.ctrlKey && event.shiftKey && event.key.toLowerCase() === "r") {
        event.preventDefault();
        const confirmed = window.confirm(
          "¿Restablecer el onboarding? Se mostrará de nuevo la próxima vez que recargues.",
        );
        if (confirmed) {
          window.localStorage.removeItem(STORAGE_KEY);
        }
      }
    };
    window.addEventListener("keydown", resetOnboarding);

    return () => {
      cancelled = true;
      controller.abort();
      clearInterval(interval);
      window.removeEventListener("keydown", resetOnboarding);
    };
  }, []);

  return (
    <header
      className={cn(
        "glass sticky top-0 z-30 flex h-14 items-center justify-between px-4 md:px-6",
      )}
    >
      <Link
        href="/"
        className="flex items-center gap-2 text-sm font-semibold tracking-tight"
      >
        <span
          aria-hidden
          className="inline-block size-2.5 rounded-full bg-accent shadow-[0_0_0_3px_color-mix(in_oklch,var(--accent)_25%,transparent)]"
        />
        jobs-finder
      </Link>

      <HealthIndicator state={health} />
    </header>
  );
}

function HealthIndicator({
  state,
}: {
  state: HealthState;
}): React.ReactElement {
  const { Icon, label, className } = (() => {
    switch (state) {
      case "ok":
        return {
          Icon: CircleCheck,
          label: "Backend reachable",
          className: "text-emerald-500",
        };
      case "degraded":
        return {
          Icon: CircleAlert,
          label: "Backend degraded",
          className: "text-amber-500",
        };
      case "down":
        return {
          Icon: CircleAlert,
          label: "Backend unreachable",
          className: "text-red-500",
        };
      case "loading":
      default:
        return {
          Icon: CircleDashed,
          label: "Checking backend",
          className: "text-muted-foreground",
        };
    }
  })();

  return (
    <div
      className="flex items-center gap-2 text-xs text-muted-foreground"
      role="status"
      aria-live="polite"
    >
      <Icon
        data-icon="inline-start"
        className={cn("size-4", className)}
        aria-hidden
      />
      <span className="hidden sm:inline">{label}</span>
    </div>
  );
}
