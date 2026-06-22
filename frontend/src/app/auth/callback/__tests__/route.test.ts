import { describe, it, expect, vi, beforeEach } from "vitest";
import { NextRequest } from "next/server";
import { GET } from "../route";
import { authCopy } from "@/lib/authCopy";

// Server-side supabase client mock — exchangeCodeForSession is the
// only method the callback handler exercises.
const exchangeCodeForSession = vi.fn(async (_code: string) => ({
  data: { user: { id: "user-1", email: "u@example.com" } },
  error: null as Error | null,
}));

vi.mock("@/lib/supabase/server", () => ({
  createClient: async () => ({
    auth: {
      exchangeCodeForSession: (code: string) => exchangeCodeForSession(code),
    },
  }),
}));

beforeEach(() => {
  exchangeCodeForSession.mockClear();
  // Reset to default success shape
  exchangeCodeForSession.mockResolvedValue({
    data: { user: { id: "user-1", email: "u@example.com" } },
    error: null,
  });
});

/**
 * Build a NextRequest that may include a `NEXT_LOCALE` cookie (mimicking
 * the cookie the LanguageSwitcher writes client-side, REQ-I18N-016).
 *
 * `new NextRequest(url, { headers })` is required (NOT `new Request(...)`)
 * because the callback reads `request.cookies.get(...)`, which only exists
 * on the NextRequest class — the underlying Request polyfill doesn't have
 * a `cookies` property, so a `Request`-cast throws "Cannot read properties
 * of undefined (reading 'get')".
 */
function makeRequest(
  path: string,
  options: { locale?: "es" | "en" } = {},
): NextRequest {
  const url = `http://localhost:3000${path}`;
  const headers = new Headers();
  if (options.locale) {
    headers.append("cookie", `NEXT_LOCALE=${options.locale}`);
  }
  return new NextRequest(url, { headers });
}

describe("auth/callback — ?next= open-redirect defense (REQ-AUTH-022)", () => {
  it("valid path → redirects there after exchangeCodeForSession", async () => {
    const res = await GET(makeRequest("/auth/callback?code=abc&next=/reset-password"));
    expect(exchangeCodeForSession).toHaveBeenCalledWith("abc");
    expect(res.headers.get("location")).toBe("http://localhost:3000/reset-password");
  });

  it("missing next → falls back to /dashboard", async () => {
    const res = await GET(makeRequest("/auth/callback?code=abc"));
    expect(res.headers.get("location")).toBe("http://localhost:3000/dashboard");
  });

  it("protocol-relative //evil → falls back to /dashboard", async () => {
    const res = await GET(makeRequest("/auth/callback?code=abc&next=//evil.com"));
    expect(res.headers.get("location")).toBe("http://localhost:3000/dashboard");
  });

  it("absolute URL https://evil → falls back to /dashboard", async () => {
    const res = await GET(makeRequest("/auth/callback?code=abc&next=https://evil.com"));
    expect(res.headers.get("location")).toBe("http://localhost:3000/dashboard");
  });

  it("backslash-trick /\\\\evil → falls back to /dashboard", async () => {
    const res = await GET(makeRequest("/auth/callback?code=abc&next=/\\evil.com"));
    expect(res.headers.get("location")).toBe("http://localhost:3000/dashboard");
  });

  it("empty next → falls back to /dashboard", async () => {
    const res = await GET(makeRequest("/auth/callback?code=abc&next="));
    expect(res.headers.get("location")).toBe("http://localhost:3000/dashboard");
  });

  it("missing code → does NOT call exchangeCodeForSession, redirects to next path", async () => {
    const res = await GET(makeRequest("/auth/callback?next=/reset-password"));
    expect(exchangeCodeForSession).not.toHaveBeenCalled();
    expect(res.headers.get("location")).toBe("http://localhost:3000/reset-password");
  });

  it("exchangeCodeForSession rejects → redirects to /login?error=…", async () => {
    exchangeCodeForSession.mockResolvedValueOnce({
      data: { user: { id: "user-1", email: "u@example.com" } },
      error: new Error("bad code"),
    });
    const res = await GET(makeRequest("/auth/callback?code=bad&next=/reset-password"));
    expect(res.headers.get("location")).toBe(
      `http://localhost:3000/login?error=${encodeURIComponent("bad code")}`,
    );
  });

  it("regression: next=/forgot-password is allowed (round-trip)", async () => {
    const res = await GET(makeRequest("/auth/callback?code=abc&next=/forgot-password"));
    expect(res.headers.get("location")).toBe("http://localhost:3000/forgot-password");
  });

  it("regression: preserves authCopy import (no dead imports)", () => {
    expect(authCopy.forgot.title).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// Locale-aware redirect target (REQ-I18N-016, REQ-I18N-021). v2 uses
// `localePrefix: 'as-needed'`, so the OAuth callback must produce
// locale-prefixed redirect URLs when the user is in a non-default locale.
// The prefix is derived from the `NEXT_LOCALE` cookie; the `?next=`
// query parameter is preserved as-is (only the prefix is added).
// ---------------------------------------------------------------------------

describe("auth/callback — locale-aware redirect (REQ-I18N-016, v2 contract)", () => {
  it("no NEXT_LOCALE cookie → /dashboard (default locale, no prefix)", async () => {
    const res = await GET(makeRequest("/auth/callback?code=abc"));
    expect(res.headers.get("location")).toBe("http://localhost:3000/dashboard");
  });

  it("NEXT_LOCALE=es cookie → /dashboard (default locale, no prefix)", async () => {
    const res = await GET(
      makeRequest("/auth/callback?code=abc", { locale: "es" }),
    );
    expect(res.headers.get("location")).toBe("http://localhost:3000/dashboard");
  });

  it("NEXT_LOCALE=en cookie + no next → /en/dashboard", async () => {
    const res = await GET(
      makeRequest("/auth/callback?code=abc", { locale: "en" }),
    );
    expect(res.headers.get("location")).toBe(
      "http://localhost:3000/en/dashboard",
    );
  });

  it("NEXT_LOCALE=en cookie + next=/reset-password → /en/reset-password", async () => {
    const res = await GET(
      makeRequest("/auth/callback?code=abc&next=/reset-password", {
        locale: "en",
      }),
    );
    expect(res.headers.get("location")).toBe(
      "http://localhost:3000/en/reset-password",
    );
  });

  it("NEXT_LOCALE=en cookie + next=/jobs/123 → /en/jobs/123", async () => {
    const res = await GET(
      makeRequest("/auth/callback?code=abc&next=/jobs/123", { locale: "en" }),
    );
    expect(res.headers.get("location")).toBe(
      "http://localhost:3000/en/jobs/123",
    );
  });

  it("NEXT_LOCALE=en cookie + next=/en/dashboard (already prefixed) → unchanged (no double-prefix)", async () => {
    const res = await GET(
      makeRequest("/auth/callback?code=abc&next=/en/dashboard", {
        locale: "en",
      }),
    );
    expect(res.headers.get("location")).toBe(
      "http://localhost:3000/en/dashboard",
    );
  });

  it("NEXT_LOCALE=en cookie + exchangeCodeForSession rejects → /en/login?error=…", async () => {
    exchangeCodeForSession.mockResolvedValueOnce({
      data: { user: { id: "user-1", email: "u@example.com" } },
      error: new Error("bad code"),
    });
    const res = await GET(
      makeRequest("/auth/callback?code=bad&next=/dashboard", { locale: "en" }),
    );
    expect(res.headers.get("location")).toBe(
      `http://localhost:3000/en/login?error=${encodeURIComponent("bad code")}`,
    );
  });

  it("NEXT_LOCALE=fr (unknown) → falls back to default /dashboard (no /fr/ prefix)", async () => {
    // Unknown locale values are rejected by readLocalePrefix; the
    // callback falls back to the default-locale empty prefix so the
    // redirect always lands on a real route.
    const url = "http://localhost:3000/auth/callback?code=abc";
    const headers = new Headers();
    headers.append("cookie", "NEXT_LOCALE=fr");
    const req = new NextRequest(url, { headers });
    const res = await GET(req);
    expect(res.headers.get("location")).toBe("http://localhost:3000/dashboard");
  });
});