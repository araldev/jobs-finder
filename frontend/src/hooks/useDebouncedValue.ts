"use client";

import { useEffect, useState } from "react";

/**
 * Debounce a value: returns `value` after it has stayed unchanged
 * for `delayMs` milliseconds. Resets the timer on every change.
 *
 * Cancellation is handled by the cleanup function in useEffect, so
 * a quick succession of updates only fires one trailing update.
 */
export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState<T>(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);

  return debounced;
}
