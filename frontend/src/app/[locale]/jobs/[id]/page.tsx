"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { useParams, useRouter } from "next/navigation";
import { JobDetailContent } from "@/components/jobs/JobDetailContent";
import { JobDetailAside } from "@/components/jobs/JobDetailAside";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { ArrowLeft } from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import { markJobAsOpened } from "@/lib/chat-storage";
import { ChatDialog } from "@/components/chat/ChatDialog";
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
 */
export default function PublicJobDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = typeof params.id === "string" ? params.id : "";
  const [user, setUser] = useState<{ email?: string } | null>(null);
  const supabase = createClient();

  const { data: job, isLoading, error, refetch } = useJobDetail(id);

  // Mark job as opened when loaded
  useEffect(() => {
    if (job?.id) {
      markJobAsOpened(job.id);
    }
  }, [job?.id]);

  // Check auth state
  useEffect(() => {
    const checkAuth = async () => {
      const { data } = await supabase.auth.getSession();
      setUser(data.session?.user ?? null);
    };
    checkAuth();
  }, [supabase]);

  async function handleLogout() {
    await supabase.auth.signOut();
    setUser(null);
  }

  const errorMessage =
    error instanceof Error ? error.message : error ? "Error loading job" : null;

  return (
    <div className="min-h-screen bg-background">
      {/* Navigation */}
      <nav className="sticky top-0 z-50 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="container mx-auto flex h-16 items-center justify-between px-4">
          <Link href="/" className="flex items-center gap-2">
            <Image src="/favicon.svg" alt="Jobs Finder" width={36} height={36} className="h-9 w-9" />
            <span className="font-display text-xl font-bold">Jobs Finder</span>
          </Link>

          <div className="hidden items-center gap-6 md:flex">
            {user ? (
              <div className="flex items-center gap-4">
                <Link
                  href="/settings"
                  className="text-sm text-muted-foreground transition-colors hover:text-foreground"
                >
                  {user.email}
                </Link>
                <Button variant="outline" size="sm" onClick={handleLogout}>
                  Cerrar sesión
                </Button>
              </div>
            ) : (
              <div className="flex items-center gap-3">
                <Link href="/login">
                  <Button variant="ghost" size="sm">Iniciar sesión</Button>
                </Link>
                <Link href="/login">
                  <Button size="sm">Registrarse</Button>
                </Link>
              </div>
            )}
          </div>
        </div>
      </nav>

      {/* Content */}
      <div className="container mx-auto px-4 py-6">
        <Button variant="ghost" size="sm" onClick={() => router.back()} className="mb-6">
          <ArrowLeft className="mr-1 h-4 w-4" />
          Volver atrás
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
              Reintentar
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
