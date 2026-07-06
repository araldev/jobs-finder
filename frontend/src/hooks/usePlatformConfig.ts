"use client";

import { useState, useEffect, useCallback } from "react";
import type { Source } from "@/types/job";
import { SOURCES } from "@/types/job";

const STORAGE_KEY = "platform-config";

const DEFAULT_ENABLED: Source[] = [...SOURCES];

function readStored(): Source[] {
  if (typeof window === "undefined") return DEFAULT_ENABLED;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_ENABLED;
    const parsed = JSON.parse(raw);
    if (
      !Array.isArray(parsed) ||
      parsed.some((s: unknown) => !SOURCES.includes(s as Source))
    ) {
      return DEFAULT_ENABLED;
    }
    return parsed as Source[];
  } catch {
    return DEFAULT_ENABLED;
  }
}

export function usePlatformConfig() {
  // Start with the default — identical on server and client for
  // the first render. `readStored()` is NOT called here because in
  // SSR it returns the default while on the client it could return
  // a custom list from localStorage, causing a hydration mismatch.
  const [enabledSources, setEnabledSources] = useState<Source[]>(DEFAULT_ENABLED);

  useEffect(() => {
    // Hydrate from localStorage AFTER mount (post-first-render).
    const stored = readStored();
    setEnabledSources(stored);

    // Listen for storage changes (cross-tab sync).
    const onStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY) setEnabledSources(readStored());
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  // Persist to localStorage whenever enabledSources changes.
  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(enabledSources));
  }, [enabledSources]);

  const toggleSource = useCallback((source: Source) => {
    setEnabledSources((prev) =>
      prev.includes(source)
        ? prev.filter((s) => s !== source)
        : [...prev, source],
    );
  }, []);

  const setAllEnabled = useCallback((enabled: boolean) => {
    setEnabledSources(enabled ? [...SOURCES] : []);
  }, []);

  const isEnabled = useCallback(
    (source: Source) => enabledSources.includes(source),
    [enabledSources],
  );

  const allEnabled = enabledSources.length === SOURCES.length;
  const noneEnabled = enabledSources.length === 0;

  return {
    enabledSources,
    toggleSource,
    setAllEnabled,
    isEnabled,
    allEnabled,
    noneEnabled,
  } as const;
}
