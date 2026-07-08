"use client";

import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { JobDetailContent } from "@/components/jobs/JobDetailContent";
import { JobDetailAside } from "@/components/jobs/JobDetailAside";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { ArrowLeft } from "lucide-react";
import { markJobAsOpened } from "@/lib/chat-storage";
import { ChatDialog } from "@/components/chat/ChatDialog";
import { Header } from "@/components/layout/Header";
import { Footer } from "@/components/layout/Footer";
import { useJobDetail } from "@/hooks/useJobDetail";

/**
 * Public job detail page (REQ-CACHEUX-004).
 *
 * Migrated from raw `useState` + `useEffect` + `fetch` to the
 * existing `useJobDetail(id)` hook. The migration:
 *   1. Joins the shared React Query cache (5min `staleTime` +
 *      window-focus refetch per `providers.tsx`).
 *   2. Removes ~25 lines of local state management.
 *   3. Preserves `markJobAsOpened(id)` side-effect + auth-check
 *      useEffect (REQ-MAINT-017).
 *   4. Behavioral equivalence: same components render for the
 *      loading / data / error branches.
 *
 * Uses the same Header component as the rest of the app
 * (Header.tsx + AuthStatus) for consistent auth/nav UI.
 */
export default function PublicJobDetailPage() {
  const params = useParams();
  const router = useRouter();
  const t = useTranslations("Jobs");
  const te = useTranslations("JobsErrors");
  const tc = useTranslations("Common");
  const id = typeof params.id === "string" ? params.id : "";

  const { data: job, isLoading, error, refetch } = useJobDetail(id);

  // Mark job as opened when loaded
  useEffect(() => {
    if (job?.id) {
      markJobAsOpened(job.id);
    }
  }, [job?.id]);

  const errorMessage =
    error instanceof Error ? error.message : error ? te("detailFailed") : null;

  return (
    <div className="min-h-screen flex flex-col bg-background">
      <Header />

      {/* Content — flex-1 pushes footer to bottom when content is short */}
      <div className="flex-1 container mx-auto px-4 py-6">
        <Button variant="ghost" size="sm" onClick={() => router.back()} className="mb-6">
          <ArrowLeft className="mr-1 h-4 w-4" />
          {tc("back")}
        </Button>

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

        {errorMessage && (
          <div className="py-16 text-center">
            <p className="text-muted-foreground">{errorMessage}</p>
            <Button variant="outline" className="mt-4" onClick={() => void refetch()}>
              {tc("retry")}
            </Button>
          </div>
        )}

        {job && !isLoading && (
          <div className="flex gap-6">
            <div className="flex-1 min-w-0">
              <JobDetailContent job={job} />
            </div>
            <JobDetailAside job={job} />
          </div>
        )}
      </div>
      <ChatDialog />
      <Footer />
    </div>
  );
}
