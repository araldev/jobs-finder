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
  const [enabledSources, setEnabledSources] = useState<Source[]>(readStored);

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
