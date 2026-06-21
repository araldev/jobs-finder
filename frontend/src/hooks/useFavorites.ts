"use client";

import { useState, useEffect, useCallback } from "react";
import type { Job } from "@/types/job";
import { JOBS_FINDER_STORAGE_KEYS } from "@/lib/auth/storageKeys";

const STORAGE_KEY = JOBS_FINDER_STORAGE_KEYS.favorites;

function readFavorites(): Job[] {
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

function writeFavorites(jobs: Job[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(jobs));
  } catch {
    // localStorage full or unavailable — silently ignore
  }
}

export interface UseFavoritesReturn {
  favorites: Job[];
  isFavorite: (id: string) => boolean;
  toggleFavorite: (job: Job) => void;
  removeFavorite: (id: string) => void;
  favoriteCount: number;
}

export function useFavorites(): UseFavoritesReturn {
  const [favorites, setFavorites] = useState<Job[]>(() => {
    if (typeof window === "undefined") return [];
    return readFavorites();
  });

  // Cross-tab sync via storage event
  useEffect(() => {
    const handleStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY) {
        setFavorites(readFavorites());
      }
    };
    window.addEventListener("storage", handleStorage);
    return () => window.removeEventListener("storage", handleStorage);
  }, []);

  const isFavorite = useCallback(
    (id: string) => favorites.some((j) => j.id === id),
    [favorites],
  );

  const toggleFavorite = useCallback(
    (job: Job) => {
      setFavorites((prev) => {
        const exists = prev.some((j) => j.id === job.id);
        const next = exists
          ? prev.filter((j) => j.id !== job.id)
          : [...prev, job];
        writeFavorites(next);
        return next;
      });
    },
    [],
  );

  const removeFavorite = useCallback(
    (id: string) => {
      setFavorites((prev) => {
        const next = prev.filter((j) => j.id !== id);
        writeFavorites(next);
        return next;
      });
    },
    [],
  );

  return {
    favorites,
    isFavorite,
    toggleFavorite,
    removeFavorite,
    favoriteCount: favorites.length,
  };
}
