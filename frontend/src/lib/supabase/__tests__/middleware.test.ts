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

