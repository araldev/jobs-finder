"use client";

import { motion } from "motion/react";
import { ArrowUpRight, Briefcase, MapPin } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { SOURCE_BADGE_COLORS, type Job, type Source } from "@/lib/types";
import { formatRelativeTime } from "@/lib/format";

interface JobCardProps {
  readonly job: Job;
}

const SOURCE_LABELS: Record<Source, string> = {
  linkedin: "LinkedIn",
  indeed: "Indeed",
  infojobs: "InfoJobs",
};

/**
 * One result card. Solid background (no glass — legibility over
 * decoration), brand-coloured source badge per source, hover
 * lift via motion.div. The whole card is a link to the original
 * posting.
 */
export function JobCard({ job }: JobCardProps): React.ReactElement {
  return (
    <motion.a
      href={job.url}
      target="_blank"
      rel="noopener noreferrer"
      className="group block rounded-2xl focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
      whileHover={{ y: -4 }}
      transition={{ type: "spring", stiffness: 380, damping: 28 }}
      aria-label={`${job.title} en ${job.company}`}
    >
      <Card className="h-full border-border/60 transition-shadow group-hover:shadow-lg group-hover:shadow-accent/10">
        <CardContent className="flex h-full flex-col gap-3">
          <div className="flex flex-wrap items-center gap-1.5">
            {job.sources.map((source) => (
              <Badge
                key={source}
                className={cn("rounded-full px-2 py-0.5 text-[10px] font-semibold tracking-wide uppercase", SOURCE_BADGE_COLORS[source])}
              >
                {SOURCE_LABELS[source]}
              </Badge>
            ))}
            <span className="ml-auto text-xs text-muted-foreground">
              {formatRelativeTime(job.posted_at)}
            </span>
          </div>
          <div>
            <h3 className="text-base leading-snug font-semibold tracking-tight">
              {job.title}
            </h3>
            <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
              <span className="inline-flex items-center gap-1">
                <Briefcase aria-hidden className="size-3.5" />
                {job.company}
              </span>
              <span className="inline-flex items-center gap-1">
                <MapPin aria-hidden className="size-3.5" />
                {job.location}
              </span>
            </div>
          </div>
          <div className="mt-auto flex items-center justify-end text-xs text-accent">
            Ver oferta
            <ArrowUpRight aria-hidden className="size-3.5" />
          </div>
        </CardContent>
      </Card>
    </motion.a>
  );
}
