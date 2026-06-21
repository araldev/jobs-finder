import { JOBS_FINDER_STORAGE_KEYS } from "./storageKeys";

/**
 * Sweep every key under `STORAGE_KEY_PREFIX` ("jobs-finder-") from
 * `window.localStorage` (REQ-AUTH-012 + ADR-005).
 *
 * Called from `DeleteAccountDialog` after a successful RPC
 * `delete_current_user` and BEFORE `supabase.auth.signOut()`. The
 * order matters: cleanup first so the in-flight session can't write
 * a new key after the sweep.
 *
 * Errors are swallowed (the user is signing out anyway; a partial
 * cleanup is acceptable).
 */
export function cleanupJobsFinderLocalStorage(): void {
  if (typeof window === "undefined") return;

  const prefix = "jobs-finder-";
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
