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
  const request = new NextRequest(url);
  // The middleware skips the Supabase auth.getUser() network
  // call when there's NO Supabase auth cookie (anon traffic
  // doesn't need a /auth/v1/user roundtrip). Tests inject a
  // fake `sb-test-auth-token` cookie that matches the production
  // cookie name pattern (`sb-<project-ref>-auth-token`) so the
  // cookie-presence check passes and `userRef.current` controls
  // the mock `auth.getUser()` response.
  request.cookies.set("sb-test-auth-token", "fake-jwt");
  return request;
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

  it("DOES call auth.getUser for CHUNKED auth-token cookies (the .0 / .1 case)", async () => {
    // Regression: Supabase's JS client splits large session tokens
    // (>~4KB) across multiple cookies named `sb-<ref>-auth-token.0`,
    // `sb-<ref>-auth-token.1`, etc. The previous middleware check
    // (`startsWith('sb-') && endsWith('-auth-token')`) missed the
    // chunked cookies, so logged-in users with chunked tokens were
    // treated as anon and bounced to /login. The current check uses
    // a regex that matches both the single-cookie and the chunked
    // variants. We assert the response is 200 (not 307 to /login)
    // for a logged-in user on /dashboard.
    userRef.current = { id: "u", email: "u@example.com" };
    const request = new NextRequest("http://localhost:3000/dashboard");
    // Set BOTH chunked cookies (mimicking a chunked token).
    request.cookies.set("sb-kpdhgvutrjirtadotlai-auth-token.0", "chunk-0");
    request.cookies.set("sb-kpdhgvutrjirtadotlai-auth-token.1", "chunk-1");
    const res = await updateSession(request);
    // Logged-in user → middleware passes through (200), NOT
    // redirect to /login (307). If the regex check missed the
    // chunked cookies, user would be null and the middleware
    // would 307-redirect to /login.
    expect(res.status).toBe(200);
  });

  it("does NOT call auth.getUser when no Supabase auth cookie is present", async () => {
    // Regression: anon traffic (no session cookie) used to hit
    // Supabase on every middleware run, failing noisily when
    // Supabase was unreachable. The middleware now short-circuits
    // the Supabase call when there's no `sb-*-auth-token` cookie
    // (anon users have no session to refresh).
    const getUserSpy = vi.fn(async () => ({
      data: { user: null },
      error: null,
    }));
    vi.doMock("@supabase/ssr", () => ({
      createServerClient: () => ({ auth: { getUser: getUserSpy } }),
    }));
    const request = new NextRequest("http://localhost:3000/");
    // Deliberately NO cookie set.
    await updateSession(request);
    expect(getUserSpy).not.toHaveBeenCalled();
    vi.doUnmock("@supabase/ssr");
  });
});

