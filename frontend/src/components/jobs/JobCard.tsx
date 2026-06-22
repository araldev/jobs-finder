"use client";

import { motion } from "framer-motion";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { ExternalLink, MapPin, Calendar, Check } from "lucide-react";
import type { Job } from "@/types/job";
import type { Locale } from "@/i18n/routing";
import { PlatformBadge } from "./PlatformBadge";
import { FavoriteButton } from "./FavoriteButton";
import { formatRelativeDate } from "@/lib/formatters";

interface JobCardProps {
  job: Job;
  index?: number;
  openedJobIds?: Set<string>;
}

export function JobCard({ job, index = 0, openedJobIds }: JobCardProps) {
  const t = useTranslations("Jobs");
  const locale = useLocale() as Locale;
  const isOpened = openedJobIds?.has(job.id);
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        type: "spring",
        bounce: 0.1,
        duration: 0.4,
        delay: Math.min(index, 5) * 0.06,
      }}
      layout
    >
      <Link
        href={`/jobs/${job.id}`}
        className="group block rounded-xl border bg-card p-4 shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-lg hover:border-primary/20 hover:shadow-primary/5"
      >
        {/* Badges row */}
        <div className="mb-2 flex flex-wrap items-center gap-2">
          {job.source && <PlatformBadge platform={job.source} />}
          {isOpened && (
            <span className="inline-flex items-center gap-1 rounded bg-emerald-100 px-1.5 py-0.5 text-xs font-medium text-emerald-700">
              <Check className="h-3 w-3" />
              {t("detail.applyNow")}
            </span>
          )}
        </div>

        {/* Title */}
        <h3 className="line-clamp-2 font-display font-semibold leading-snug group-hover:text-primary transition-colors">
          {job.title}
        </h3>

        {/* Meta: company + location */}
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
          <span>{job.company}</span>
          {job.location && (
            <span className="inline-flex items-center gap-1">
              <MapPin className="h-3 w-3" />
              {job.location}
            </span>
          )}
        </div>

        {/* Footer: date + favorite + external link */}
        <div className="mt-3 flex items-center justify-between border-t pt-3">
          <div className="flex items-center gap-1 text-xs text-muted-foreground">
            <Calendar className="h-3 w-3" />
            {job.posted_at ? formatRelativeDate(job.posted_at, locale) : t("notSpecified")}
          </div>
          <div className="flex items-center gap-1">
            <FavoriteButton job={job} size="sm" />
            {job.url && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  e.preventDefault();
                  window.open(job.url, "_blank", "noopener,noreferrer");
                }}
                className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground hover:bg-muted"
                title={t("card.openExternal")}
                aria-label={t("card.openExternal")}
              >
                <ExternalLink className="h-3.5 w-3.5" />
                {t("card.apply")}
              </button>
            )}
          </div>
        </div>
      </Link>
    </motion.div>
  );
}