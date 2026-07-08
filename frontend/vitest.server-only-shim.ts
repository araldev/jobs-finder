/**
 * No-op shim for the `server-only` package, used by vitest so we can
 * import server-only modules in unit tests. The real `server-only`
 * package throws when imported from a client module; in tests we want
 * to load the module's actual implementation.
 *
 * Mirrors the Next.js webpack handling of `server-only` in the
 * `serverExternalPackages` / `serverComponentsExternalPackages`
 * config (Next.js treats it as an empty module on the server).
 */
export {};
