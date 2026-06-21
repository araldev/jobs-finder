import { JOBS_FINDER_STORAGE_KEYS, STORAGE_KEY_PREFIX } from "./storageKeys";

/**
 * Sweep every key under `STORAGE_KEY_PREFIX` ("jobs-finder-") from
 * `window.localStorage` (REQ-AUTH-012 + ADR-005).
 *
 * Called from `DeleteAccountDialog` ONLY after a successful
 * `supabase.rpc('delete_current_user')` and BEFORE
 * `supabase.auth.signOut()`. The RPC MUST run first — if the
 * server-side delete fails, the user's data must stay intact in
 * localStorage so the UI doesn't show an empty state while the
 * Supabase data is still there. See REQ-AUTH-012.
 *
 * Errors are swallowed (the user is signing out anyway; a partial
 * cleanup is acceptable).
 */
export function cleanupJobsFinderLocalStorage(): void {
  if (typeof window === "undefined") return;

  const prefix = STORAGE_KEY_PREFIX;
  try {
    const keys: string[] = [];
    for (let i = 0; i < window.localStorage.length; i++) {
      const key = window.localStorage.key(i);
      if (key && key.startsWith(prefix)) {
        keys.push(key);
      }
    }
    for (const key of keys) {
      window.localStorage.removeItem(key);
    }
  } catch {
    // localStorage unavailable (private mode, quota, etc.) — ignore.
  }

  // The typed constant is the source of truth; the prefix sweep is
  // a defensive backstop in case a future code path wrote a
  // `jobs-finder-*` key without going through the constant.
  void JOBS_FINDER_STORAGE_KEYS;
}
