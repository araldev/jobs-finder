import { describe, it, expect, vi } from "vitest";
import { NextRequest } from "next/server";
import { updateSession } from "../middleware";

// Mock the @supabase/ssr module so the middleware can talk to a
// fake `auth.getUser()` that we control per-test via a global ref.
const userRef: { current: { id: string; email: string } | null } = {
  current: null,
};

vi.mock("@supabase/ssr", () => ({
  createServerClient: () => ({
    auth: {
      getUser: async () => ({ data: { user: userRef.current }, error: null }),
    },
  }),
}));

function makeRequest(pathname: string): NextRequest {
  const url = `http://localhost:3000${pathname}`;
  return new NextRequest(url);
}

async function runMiddleware(pathname: string, hasUser: boolean) {
  userRef.current = hasUser ? { id: "user-1", email: "u@example.com" } : null;
  return await updateSession(makeRequest(pathname));
}

describe("updateSession — publicPaths whitelist (REQ-AUTH-021)", () => {
  it("/forgot-password with NO user → does NOT redirect to /login", async () => {
    const res = await runMiddleware("/forgot-password", false);
    expect(res.status).toBe(200);
    expect(res.headers.get("location") ?? "").not.toMatch(/\/login/);
  });

  it("/reset-password with NO user → does NOT redirect to /login", async () => {
    const res = await runMiddleware("/reset-password", false);
    expect(res.status).toBe(200);
    expect(res.headers.get("location") ?? "").not.toMatch(/\/login/);
  });

  it("/forgot-password with user present → NOT redirected to /dashboard", async () => {
    const res = await runMiddleware("/forgot-password", true);
    expect(res.status).toBe(200);
    expect(res.headers.get("location") ?? "").not.toMatch(/\/dashboard/);
  });

  it("/reset-password with user present → NOT redirected to /dashboard", async () => {
    const res = await runMiddleware("/reset-password", true);
    expect(res.status).toBe(200);
    expect(res.headers.get("location") ?? "").not.toMatch(/\/dashboard/);
  });

  it("regression: /login with NO user still renders (public path)", async () => {
    const res = await runMiddleware("/login", false);
    expect(res.status).toBe(200);
    expect(res.headers.get("location") ?? "").not.toMatch(/\/dashboard/);
  });

  it("regression: /login with user → redirected to /dashboard (existing branch)", async () => {
    const res = await runMiddleware("/login", true);
    expect(res.status).toBeGreaterThanOrEqual(300);
    expect(res.headers.get("location") ?? "").toMatch(/\/dashboard/);
  });

  it("protected /dashboard with NO user → redirected to /login", async () => {
    const res = await runMiddleware("/dashboard", false);
    expect(res.status).toBeGreaterThanOrEqual(300);
    expect(res.headers.get("location") ?? "").toMatch(/\/login/);
  });

  it("protected /dashboard with user → renders (200)", async () => {
    const res = await runMiddleware("/dashboard", true);
    expect(res.status).toBe(200);
  });
});

// ---------------------------------------------------------------------------
// Locale-aware auth redirects (REQ-I18N-020, v2 contract).
//
// v2 uses `localePrefix: 'as-needed'`. When an unauthenticated user
// hits a protected route, the auth bounce must land on the locale-correct
// login path — e.g. `/en/dashboard` → `/en/login`, not `/login`. The
// `deriveLocalePrefix` helper (in middleware.ts) inspects the original
// URL and returns the locale prefix string for non-default locales.
// ---------------------------------------------------------------------------

describe("updateSession — locale-aware auth redirect (REQ-I18N-020)", () => {
  it("/en/dashboard with NO user → redirected to /en/login (locale-aware bounce)", async () => {
    const res = await runMiddleware("/en/dashboard", false);
    expect(res.status).toBeGreaterThanOrEqual(300);
    expect(res.headers.get("location")).toBe("http://localhost:3000/en/login");
  });

  it("/en/search with NO user → redirected to /en/login", async () => {
    const res = await runMiddleware("/en/search", false);
    expect(res.status).toBeGreaterThanOrEqual(300);
    expect(res.headers.get("location")).toBe("http://localhost:3000/en/login");
  });

  it("/en/settings with NO user → redirected to /en/login", async () => {
    const res = await runMiddleware("/en/settings", false);
    expect(res.status).toBeGreaterThanOrEqual(300);
    expect(res.headers.get("location")).toBe("http://localhost:3000/en/login");
  });

  it("/en/login with user present → redirected to /en/dashboard (locale-aware bounce-back)", async () => {
    const res = await runMiddleware("/en/login", true);
    expect(res.status).toBeGreaterThanOrEqual(300);
    expect(res.headers.get("location")).toBe(
      "http://localhost:3000/en/dashboard",
    );
  });

  it("/en/forgot-password with NO user → does NOT redirect (public path)", async () => {
    // REQ-AUTH-021: forgot-password is part of the public auth flow,
    // so an unauthenticated user can hit it without bouncing.
    const res = await runMiddleware("/en/forgot-password", false);
    expect(res.status).toBe(200);
    expect(res.headers.get("location") ?? "").not.toMatch(/\/login/);
  });

  it("/es/dashboard with NO user → redirected to /login (default locale, no prefix)", async () => {
    // Default locale URLs do NOT get a prefix (per the localePrefix
    // 'as-needed' contract). `/es/...` paths are technically valid but
    // the default locale is unprefixed; the helper returns "" for `es`.
    const res = await runMiddleware("/es/dashboard", false);
    expect(res.status).toBeGreaterThanOrEqual(300);
    expect(res.headers.get("location")).toBe("http://localhost:3000/login");
  });
});

