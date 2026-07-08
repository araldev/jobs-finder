"use client";

import { useTranslations } from "next-intl";
import { Calendar, ExternalLink, MapPin, FileText } from "lucide-react";
import type { Job } from "@/types/job";
import { PlatformBadge } from "./PlatformBadge";
import { formatRelativeDate } from "@/lib/formatters";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { GenerateCVModal } from "./GenerateCVModal";

interface JobDetailAsideProps {
  job: Job;
}

export function JobDetailAside({ job }: JobDetailAsideProps) {
  const t = useTranslations("Jobs");
  return (
    <aside className="w-72 flex-shrink-0">
      <div className="sticky top-6 space-y-4 rounded-xl border bg-card p-4 shadow-sm">
        <div>
          <h4 className="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
            {t("card.source")}
          </h4>
          <div className="flex flex-wrap gap-1.5">
            {job.source && <PlatformBadge platform={job.source} />}
          </div>
        </div>

        <Separator />

        <div>
          <h4 className="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
            {t("detail.posted")}
          </h4>
          <p className="inline-flex items-center gap-1.5 text-sm">
            <Calendar className="h-3.5 w-3.5 text-muted-foreground" />
            {job.posted_at ? formatRelativeDate(job.posted_at) : "—"}
          </p>
        </div>

        {job.location && (
          <>
            <Separator />
            <div>
              <h4 className="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                {t("card.location")}
              </h4>
              <p className="inline-flex items-center gap-1.5 text-sm">
                <MapPin className="h-3.5 w-3.5 text-muted-foreground" />
                {job.location}
              </p>
            </div>
          </>
        )}

        <Separator />

        <Button variant="outline" className="w-full" asChild>
          <a href={job.url} target="_blank" rel="noopener noreferrer">
            <ExternalLink className="mr-2 h-4 w-4" />
            {t("detail.viewOriginal")}
          </a>
        </Button>

        <Separator />

        <GenerateCVModal
          key={job.id}
          job={job}
          trigger={
            <Button variant="default" className="w-full" type="button">
              <FileText className="mr-2 h-4 w-4" />
              {t("modal.generate")}
            </Button>
          }
        />
      </div>
    </aside>
  );
}
