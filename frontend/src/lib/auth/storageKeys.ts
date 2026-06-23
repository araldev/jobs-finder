/**
 * `jobs-finder-*` localStorage convention (REQ-AUTH-026 / ADR-005).
 *
 * Every localStorage key the frontend writes MUST be prefixed with
 * `jobs-finder-` so the account-deletion cleanup helper can sweep only
 * our keys (and leave every other app's localStorage alone on a shared
 * origin in dev).
 *
 * Future keys MUST be added here FIRST, before they ship. The cleanup
 * helper iterates `JOBS_FINDER_STORAGE_KEYS` (not `Object.keys(localStorage)`)
 * for the deterministic sweep.
 */
export const STORAGE_KEY_PREFIX = "jobs-finder-";

export const JOBS_FINDER_STORAGE_KEYS = Object.freeze({
  favorites: `${STORAGE_KEY_PREFIX}favorites`,
  chat: `${STORAGE_KEY_PREFIX}chat-v1`,
});

export type JobsFinderStorageKey =
  (typeof JOBS_FINDER_STORAGE_KEYS)[keyof typeof JOBS_FINDER_STORAGE_KEYS];
