"use client";

import { useState, useEffect, useCallback } from "react";

interface CVCountResponse {
  total_today: number;
}

export interface UseCVAdaptedReturn {
  cvAdaptedCount: number;
  incrementCVAdapted: () => void;
}

/**
 * Track how many CVs the user has generated today.
 *
 * On mount, fetches the count from `/api/cv/count` (which proxies
 * to the backend `GET /cv/count`, returning the server-side daily
 * total from the engagement events table).
 *
 * After a successful CV generation, call `incrementCVAdapted()`
 * to optimistically bump the local count (the backend already
 * recorded the event server-side). On the next page load the
 * true count is fetched from the API.
 */
export function useCVAdapted(): UseCVAdaptedReturn {
  const [cvAdaptedCount, setCVAdaptedCount] = useState<number>(0);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/cv/count")
      .then((res) => {
        if (!res.ok) return null;
        return res.json() as Promise<CVCountResponse>;
      })
      .then((data) => {
        if (!cancelled && data) {
          setCVAdaptedCount(data.total_today);
        }
      })
      .catch(() => {
        // Backend unreachable — keep default 0
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const incrementCVAdapted = useCallback(() => {
    setCVAdaptedCount((prev) => prev + 1);
  }, []);

  return { cvAdaptedCount, incrementCVAdapted };
}
