"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { PageTransition } from "@/components/layout/PageTransition";
import { JobDetailContent } from "@/components/jobs/JobDetailContent";
import { JobDetailAside } from "@/components/jobs/JobDetailAside";
import { useJobDetail } from "@/hooks/useJobDetail";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/shared/ErrorState";
import { Button } from "@/components/ui/button";

export default function JobDetailPage() {
  const params = useParams();
  const id = typeof params.id === "string" ? params.id : "";
  const { data: job, isLoading, isError, refetch } = useJobDetail(id);

  return (
    <PageTransition>
      <div className="mb-6">
        <Button variant="ghost" size="sm" asChild>
          <Link href="/" className="inline-flex items-center gap-1">
            <ArrowLeft className="h-4 w-4" />
            Back to Dashboard
          </Link>
        </Button>
      </div>

      {isLoading && (
        <div className="flex gap-6">
          <div className="flex-1 space-y-4">
            <Skeleton className="h-8 w-3/4" />
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-32 w-full" />
          </div>
          <Skeleton className="hidden w-72 lg:block" />
        </div>
      )}

      {isError && (
        <ErrorState
          message="Could not load job details"
          onRetry={() => refetch()}
        />
      )}

      {job && !isLoading && (
        <div className="flex gap-6">
          <div className="flex-1 min-w-0">
            <JobDetailContent job={job} />
          </div>
          <JobDetailAside job={job} />
        </div>
      )}
    </PageTransition>
  );
}
