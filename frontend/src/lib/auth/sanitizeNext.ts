/**
 * Open-redirect defense for `?next=` query params.
 *
 * ADR-008 (design #513) — accept only paths matching:
 *   - starts with a single `/`  (so `https://evil` is rejected)
 *   - does NOT start with `//`  (protocol-relative URLs)
 *   - does NOT start with `/\`  (backslash tricks)
 *   - is NOT the bare `/`      (must have an actual path)
 *
 * Anything else falls back to `/dashboard`.
 *
 * Returns the canonical path (e.g. `/dashboard`, NOT `/Dashboard/`).
 *
 * Threat model: an attacker tricks a victim into clicking
 * `/auth/callback?code=…&next=//evil.example/phish`. Without this
 * validator, `NextResponse.redirect` follows the `//evil.example/…`
 * protocol-relative URL to a different origin, phishing the user
 * after a legitimate Supabase session-exchange.
 */
export function sanitizeNext(next: string | null): string {
  const FALLBACK = "/dashboard";

  if (!next || typeof next !== "string") return FALLBACK;
  if (!next.startsWith("/")) return FALLBACK;
  if (next.startsWith("//")) return FALLBACK;
  if (next.startsWith("/\\")) return FALLBACK;
  if (next === "/") return FALLBACK;

  return next;
}
