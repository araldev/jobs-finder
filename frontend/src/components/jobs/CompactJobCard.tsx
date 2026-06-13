"use client";

import { motion } from "framer-motion";
import Link from "next/link";
import { MapPin, ExternalLink } from "lucide-react";
import type { Job } from "@/types/job";
import { PlatformBadge } from "./PlatformBadge";
import { FavoriteButton } from "./FavoriteButton";
import { formatRelativeDate } from "@/lib/formatters";

interface CompactJobCardProps {
  job: Job;
  index?: number;
}

export function CompactJobCard({ job, index = 0 }: CompactJobCardProps) {
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
        className="group block rounded-xl border bg-card p-3 shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-lg hover:border-primary/20 hover:shadow-primary/5"
      >
        {/* Badges row */}
        <div className="mb-1.5 flex flex-wrap items-center gap-2">
          {job.source && <PlatformBadge platform={job.source} />}
        </div>

        {/* Title - single line clamp */}
        <h3 className="line-clamp-1 text-sm font-semibold font-display leading-snug group-hover:text-primary transition-colors">
          {job.title}
        </h3>

        {/* Meta: company + location (inline, small) */}
        <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
          <span className="truncate max-w-[150px]">{job.company}</span>
          {job.location && (
            <span className="inline-flex items-center gap-1">
              <MapPin className="h-3 w-3 flex-shrink-0" />
              <span className="truncate max-w-[120px]">{job.location}</span>
            </span>
          )}
        </div>

        {/* Date - no Calendar icon, no divider */}
        <div className="mt-1.5 text-xs text-muted-foreground">
          {job.posted_at ? formatRelativeDate(job.posted_at) : "Unknown"}
        </div>

        {/* Footer row: FavoriteButton + ExternalLink */}
        <div className="mt-2 flex items-center justify-end gap-1">
          <FavoriteButton job={job} size="sm" />
          <button
            type="button"
            aria-label="Open job posting"
            title="Open job posting"
            onClick={(e) => {
              e.stopPropagation();
              e.preventDefault();
              window.open(job.url, "_blank", "noopener,noreferrer");
            }}
            className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <ExternalLink className="h-4 w-4" />
          </button>
        </div>
      </Link>
    </motion.div>
  );
}
