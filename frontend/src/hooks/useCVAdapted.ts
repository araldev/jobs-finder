"use client";

import { useState, useEffect, useCallback } from "react";
import { JOBS_FINDER_STORAGE_KEYS } from "@/lib/auth/storageKeys";

const CV_ADAPTED_STORAGE_KEY = JOBS_FINDER_STORAGE_KEYS.cvAdaptedCount;

function readCVAdaptedCount(): number {
  if (typeof window === "undefined") return 0;
  try {
    const raw = localStorage.getItem(CV_ADAPTED_STORAGE_KEY);
    if (!raw) return 0;
    const parsed = JSON.parse(raw);
    return typeof parsed === "number" ? parsed : 0;
  } catch {
    return 0;
  }
}

function writeCVAdaptedCount(count: number): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(CV_ADAPTED_STORAGE_KEY, JSON.stringify(count));
  } catch {
    // localStorage full or unavailable — silently ignore
  }
}

export interface UseCVAdaptedReturn {
  cvAdaptedCount: number;
  incrementCVAdapted: () => void;
}

export function useCVAdapted(): UseCVAdaptedReturn {
  const [cvAdaptedCount, setCVAdaptedCount] = useState<number>(0);

  useEffect(() => {
    setCVAdaptedCount(readCVAdaptedCount());
  }, []);

  const incrementCVAdapted = useCallback(() => {
    setCVAdaptedCount((prev) => {
      const next = prev + 1;
      writeCVAdaptedCount(next);
      return next;
    });
  }, []);

  return { cvAdaptedCount, incrementCVAdapted };
}
