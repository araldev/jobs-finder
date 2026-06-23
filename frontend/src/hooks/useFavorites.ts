"use client";

import { useCallback, useState } from "react";
import type { Job } from "@/types/job";
import { JOBS_FINDER_STORAGE_KEYS } from "@/lib/auth/storageKeys";

const STORAGE_KEY = JOBS_FINDER_STORAGE_KEYS.favorites;

export interface UseFavoritesReturn {
  favorites: Job[];
  isFavorite: (id: string) => boolean;
  toggleFavorite: (job: Job) => void;
  removeFavorite: (id: string) => void;
  favoriteCount: number;
  isLoading: boolean;
  error: string | null;
}

async function fetchFavorites(): Promise<Job[]> {
  const res = await fetch("/api/users/me/favorites?limit=1000");
  if (!res.ok) {
    if (res.status === 401) {
      throw new Error("Unauthorized");
    }
    throw new Error("Failed to fetch favorites");
  }
  const data = await res.json();
  return data.data as Job[];
}

async function apiAddFavorite(job_id: number): Promise<void> {
  const res = await fetch("/api/users/me/favorites", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_id }),
  });
  if (!res.ok && res.status !== 404) {
    throw new Error("Failed to add favorite");
  }
}

async function apiRemoveFavorite(job_id: number): Promise<void> {
  const res = await fetch(`/api/users/me/favorites/${job_id}`, {
    method: "DELETE",
  });
  if (!res.ok && res.status !== 204) {
    throw new Error("Failed to remove favorite");
  }
}

// Fallback: localStorage-based favorites for when API is unavailable
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

export function useFavorites(): UseFavoritesReturn {
  const [favorites, setFavorites] = useState<Job[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [useLocalStorage, setUseLocalStorage] = useState(false);

  // Try to load from API first, fall back to localStorage
  const loadFavorites = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const jobs = await fetchFavorites();
      setFavorites(jobs);
      setUseLocalStorage(false);
    } catch {
      // Fall back to localStorage
      const localJobs = readLocalFavorites();
      setFavorites(localJobs);
      setUseLocalStorage(true);
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Load favorites on mount (client-side only)
  if (typeof window !== "undefined" && favorites.length === 0 && !isLoading) {
    loadFavorites();
  }

  const isFavorite = useCallback(
    (id: string) => favorites.some((j) => j.id === id),
    [favorites],
  );

  const toggleFavorite = useCallback(
    async (job: Job) => {
      const exists = favorites.some((j) => j.id === job.id);

      if (exists) {
        // Optimistic update - remove
        setFavorites((prev) => {
          const next = prev.filter((j) => j.id !== job.id);
          writeLocalFavorites(next);
          return next;
        });

        if (!useLocalStorage) {
          try {
            await apiRemoveFavorite(parseInt(job.id, 10));
          } catch {
            // Revert on error
            loadFavorites();
          }
        }
      } else {
        // Optimistic update - add
        setFavorites((prev) => {
          const next = [...prev, job];
          writeLocalFavorites(next);
          return next;
        });

        if (!useLocalStorage) {
          try {
            await apiAddFavorite(parseInt(job.id, 10));
          } catch {
            // Revert on error
            loadFavorites();
          }
        }
      }
    },
    [favorites, useLocalStorage, loadFavorites],
  );

  const removeFavorite = useCallback(
    async (id: string) => {
      // Optimistic update
      setFavorites((prev) => {
        const next = prev.filter((j) => j.id !== id);
        writeLocalFavorites(next);
        return next;
      });

      if (!useLocalStorage) {
        try {
          await apiRemoveFavorite(parseInt(id, 10));
        } catch {
          // Revert on error
          loadFavorites();
        }
      }
    },
    [useLocalStorage, loadFavorites],
  );

  return {
    favorites,
    isFavorite,
    toggleFavorite,
    removeFavorite,
    favoriteCount: favorites.length,
    isLoading,
    error,
  };
}
