"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { toast } from "sonner";
import { useTranslations } from "next-intl";
import type { Job } from "@/types/job";
import { JOBS_FINDER_STORAGE_KEYS } from "@/lib/auth/storageKeys";

const STORAGE_KEY = JOBS_FINDER_STORAGE_KEYS.favorites;
export const FAVORITES_QUERY_KEY = ["favorites"] as const;

// Snapshot of `Date.now()` taken once at module load — used as the
// `initialDataUpdatedAt` for React Query. We pass this to mark the
// empty initial data as FRESH at hydration time so React Query
// doesn't immediately refetch and overwrite the localStorage
// hydration that happens in `useEffect` below. The reference is
// stable across re-renders, so the cache fingerprint is stable too.
const INITIAL_DATA_UPDATED_AT = Date.now();

export interface UseFavoritesReturn {
  favorites: Job[];
  isFavorite: (id: string) => boolean;
  toggleFavorite: (job: Job) => void;
  removeFavorite: (job: Job) => void;
  favoriteCount: number;
  isLoading: boolean;
  error: string | null;
}

function readLocalFavorites(): Job[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed as Job[];
  } catch {
    return [];
  }
}

function writeLocalFavorites(jobs: Job[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(jobs));
  } catch {
    // localStorage full or unavailable — silently ignore
  }
}

async function fetchFavorites(): Promise<Job[]> {
  const res = await fetch("/api/users/me/favorites?limit=1000");
  if (res.status === 401) return [];
  if (!res.ok) throw new Error(`Failed to fetch favorites: ${res.status}`);
  const data = await res.json();
  return (data?.data ?? []) as Job[];
}

async function apiAddFavorite(job: Job): Promise<void> {
  const res = await fetch("/api/users/me/favorites", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job }),
  });
  if (!res.ok) {
    throw new Error(`Failed to add favorite: ${res.status}`);
  }
}

async function apiRemoveFavorite(source: string, sourceId: string): Promise<void> {
  const res = await fetch(
    `/api/users/me/favorites/${encodeURIComponent(source)}/${encodeURIComponent(sourceId)}`,
    { method: "DELETE" },
  );
  if (!res.ok && res.status !== 204) {
    throw new Error(`Failed to remove favorite: ${res.status}`);
  }
}

export function useFavorites(): UseFavoritesReturn {
  const t = useTranslations("Jobs.favorite");
  const queryClient = useQueryClient();
  // Track whether we've mounted on the client. We hydrate from
  // localStorage in a useEffect (post-mount) instead of via
  // `initialData: readLocalFavorites()` because reading localStorage
  // during the first render produces a hydration mismatch: the
  // server has no localStorage and returns `[]`, while the client
  // may return a non-empty list. With this `mounted` flag we
  // guarantee the first render on both sides returns `[]`, then
  // update the cache after mount.
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
  }, []);

  const query = useQuery<Job[]>({
    queryKey: FAVORITES_QUERY_KEY,
    queryFn: fetchFavorites,
    // `initialData: []` is identical on server and client — both
    // render an empty list at first. The `initialDataUpdatedAt`
    // marks it as fresh so React Query doesn't trigger an immediate
    // refetch that would race with the localStorage hydration below.
    initialData: [],
    initialDataUpdatedAt: INITIAL_DATA_UPDATED_AT,
    staleTime: 5 * 60 * 1000,
    refetchOnWindowFocus: true,
    retry: 1,
  });

  // Hydrate from localStorage AFTER mount. Reads `readLocalFavorites`
  // which returns `[]` if storage is empty/corrupt (server-side
  // behavior preserved for the first frame). This is the equivalent
  // of the old `initialData: readLocalFavorites()` but deferred to
  // post-mount to avoid the SSR/CSR mismatch.
  useEffect(() => {
    const local = readLocalFavorites();
    if (local.length > 0) {
      queryClient.setQueryData<Job[]>(FAVORITES_QUERY_KEY, local);
    }
    // Only run on mount (not when query.data changes — that would
    // clobber optimistic updates).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queryClient, mounted]);

  const toggleMutation = useMutation({
    mutationFn: async (job: Job) => {
      const exists = (query.data ?? []).some((j) => j.id === job.id);
      if (exists) {
        await apiRemoveFavorite(job.source, String(job.id));
      } else {
        await apiAddFavorite(job);
      }
    },
    onMutate: async (job) => {
      await queryClient.cancelQueries({ queryKey: FAVORITES_QUERY_KEY });
      const previous = queryClient.getQueryData<Job[]>(FAVORITES_QUERY_KEY) ?? [];
      const exists = previous.some((j) => j.id === job.id);
      const optimistic = exists
        ? previous.filter((j) => j.id !== job.id)
        : [...previous, job];
      queryClient.setQueryData<Job[]>(FAVORITES_QUERY_KEY, optimistic);
      writeLocalFavorites(optimistic);
      return { previous };
    },
    onError: (_err, _job, context) => {
      if (context?.previous) {
        queryClient.setQueryData<Job[]>(FAVORITES_QUERY_KEY, context.previous);
        writeLocalFavorites(context.previous);
      }
      toast.error(t("errorToggle"));
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: FAVORITES_QUERY_KEY });
    },
  });

  const removeMutation = useMutation({
    mutationFn: async (job: Job) => {
      await apiRemoveFavorite(job.source, String(job.id));
    },
    onMutate: async (job) => {
      await queryClient.cancelQueries({ queryKey: FAVORITES_QUERY_KEY });
      const previous = queryClient.getQueryData<Job[]>(FAVORITES_QUERY_KEY) ?? [];
      const optimistic = previous.filter((j) => j.id !== job.id);
      queryClient.setQueryData<Job[]>(FAVORITES_QUERY_KEY, optimistic);
      writeLocalFavorites(optimistic);
      return { previous };
    },
    onError: (_err, _job, context) => {
      if (context?.previous) {
        queryClient.setQueryData<Job[]>(FAVORITES_QUERY_KEY, context.previous);
        writeLocalFavorites(context.previous);
      }
      toast.error(t("errorToggle"));
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: FAVORITES_QUERY_KEY });
    },
  });

  const favorites = useMemo(() => query.data ?? [], [query.data]);
  const isFavorite = useCallback(
    (id: string) => favorites.some((j) => j.id === id),
    [favorites],
  );

  return {
    favorites,
    isFavorite,
    toggleFavorite: (job: Job) => toggleMutation.mutate(job),
    removeFavorite: (job: Job) => removeMutation.mutate(job),
    favoriteCount: favorites.length,
    isLoading: query.isLoading || toggleMutation.isPending || removeMutation.isPending,
    error:
      (query.error as Error | null)?.message ??
      (toggleMutation.error as Error | null)?.message ??
      (removeMutation.error as Error | null)?.message ??
      null,
  };
}
