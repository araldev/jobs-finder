"use client";

import { useCallback, useEffect, useState } from "react";
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
import type { Job } from "@/types/job";

export default function PublicJobDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = typeof params.id === "string" ? params.id : "";
  const [job, setJob] = useState<Job | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [user, setUser] = useState<{ email?: string } | null>(null);
  const supabase = createClient();

  const fetchJob = useCallback(async () => {
    try {
      const res = await fetch(`/api/jobs/${id}`);
      if (!res.ok) throw new Error("Job not found");
      const data = await res.json();
      setJob(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error loading job");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchJob();
  }, [fetchJob]);

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

        {loading && (
          <div className="flex gap-6">
            <div className="flex-1 space-y-4">
              <Skeleton className="h-8 w-3/4" />
              <Skeleton className="h-4 w-1/2" />
              <Skeleton className="h-32 w-full" />
            </div>
            <Skeleton className="hidden w-72 lg:block" />
          </div>
        )}

        {error && (
          <div className="py-16 text-center">
            <p className="text-muted-foreground">{error}</p>
            <Button variant="outline" className="mt-4" onClick={fetchJob}>
              Reintentar
            </Button>
          </div>
        )}

        {job && !loading && (
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
