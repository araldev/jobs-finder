"use client";

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import type { Job } from "@/lib/types";

/**
 * Coordinates the chat → search handoff. When the chat's `done`
 * event arrives with a filtered `jobs` array, the chat calls
 * `setOverride` so the SearchSection renders that subset instead
 * of the debounced search results. `clearOverride` restores the
 * normal flow.
 *
 * The context value is small and stable so consuming components
 * only re-render when the actual override or the clearTrigger
 * identity changes.
 */
interface JobsOverrideContextValue {
  readonly override: readonly Job[] | null;
  readonly setOverride: (jobs: readonly Job[] | null) => void;
  readonly clearOverride: () => void;
  /** Bumped on every clear so the search can force a refetch. */
  readonly clearTrigger: number;
}

const JobsOverrideContext = createContext<JobsOverrideContextValue | null>(null);

export function JobsOverrideProvider({ children }: { children: ReactNode }): React.ReactElement {
  const [override, setOverrideState] = useState<readonly Job[] | null>(null);
  const [clearTrigger, setClearTrigger] = useState(0);

  const setOverride = useCallback((jobs: readonly Job[] | null) => {
    setOverrideState(jobs);
  }, []);

  const clearOverride = useCallback(() => {
    setOverrideState(null);
    setClearTrigger((n) => n + 1);
  }, []);

  const value = useMemo<JobsOverrideContextValue>(
    () => ({ override, setOverride, clearOverride, clearTrigger }),
    [override, setOverride, clearOverride, clearTrigger],
  );

  return (
    <JobsOverrideContext.Provider value={value}>
      {children}
    </JobsOverrideContext.Provider>
  );
}

export function useJobsOverride(): JobsOverrideContextValue {
  const ctx = useContext(JobsOverrideContext);
  if (ctx === null) {
    throw new Error("useJobsOverride must be used inside a JobsOverrideProvider");
  }
  return ctx;
}
