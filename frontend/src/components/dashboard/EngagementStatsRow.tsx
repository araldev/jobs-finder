"use client";

import { Eye, FileText, Heart } from "lucide-react";
import { useTranslations } from "next-intl";

import { StatCard } from "./StatCard";
import { useOpenedJobs } from "@/lib/chat-storage";
import { useFavorites } from "@/hooks/useFavorites";
import { useCVAdapted } from "@/hooks/useCVAdapted";

/**
 * EngagementStatsRow — REQ-PDPRSC-002.
 *
 * Client island that owns the 3 "engagement" stat cards
 * (opened jobs, CVs adapted, favorites). These metrics read
 * from browser-only storage:
 *
 *   - `useOpenedJobs` — `localStorage` via `chat-storage.ts`.
 *   - `useFavorites`  — `localStorage` (favorites list).
 *   - `useCVAdapted`  — `localStorage` (CV counter).
 *
 * `localStorage` does not exist server-side, so these stats
 * CANNOT migrate to RSC. They live here as a single client
 * island inside the otherwise-RSC dashboard. The visual layout
 * (3-up responsive grid of `StatCard`s) is preserved exactly so
 * the page's CLS budget (0.002 baseline) is unaffected.
 *
 * Originally these cards lived at the bottom of `StatsCardsRow`
 * (the post-migration RSC fetches server-side stats). Splitting
 * them into this client island keeps the boundary clean:
 * server-fetchable stats stay in RSC, browser-only stats stay
 * in a client island.
 */
export function EngagementStatsRow() {
  const openedJobIds = useOpenedJobs();
  const { favoriteCount } = useFavorites();
  const { cvAdaptedCount } = useCVAdapted();
  const t = useTranslations("Dashboard");

  return (
    <div className="grid gap-4 sm:grid-cols-3">
      <StatCard
        icon={<Eye className="h-5 w-5 text-foreground/80" />}
        label={t("stats.openedJobs.label")}
        value={openedJobIds.size > 0 ? openedJobIds.size.toLocaleString() : "—"}
        accent="primary"
        delay={0.15}
      />
      <StatCard
        icon={<FileText className="h-5 w-5 text-foreground/80" />}
        label={t("stats.cvsAdapted.label")}
        value={cvAdaptedCount > 0 ? cvAdaptedCount.toLocaleString() : "—"}
        accent="secondary"
        delay={0.2}
      />
      <StatCard
        icon={<Heart className="h-5 w-5 text-foreground/80" />}
        label={t("stats.favorites.label")}
        value={favoriteCount > 0 ? favoriteCount.toLocaleString() : "—"}
        accent="muted"
        delay={0.25}
      />
    </div>
  );
}