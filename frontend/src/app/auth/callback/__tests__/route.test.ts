import { describe, it, expect, vi, beforeEach } from "vitest";
import type { NextRequest } from "next/server";
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

function makeRequest(path: string): NextRequest {
  return new Request(`http://localhost:3000${path}`) as unknown as NextRequest;
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
