// Tests for the service-role Supabase client (server-only).
//
// The service-role client bypasses RLS entirely — it's the seam
// between the Next.js server runtime and Supabase for operations
// that require direct DB access without an end-user JWT (webhook
// UPSERT, billing event append).
//
// We mock `@supabase/supabase-js` so we can:
//   - assert the lazy singleton semantics (one createClient call per
//     process lifetime),
//   - assert env-var validation (throws clear errors when keys are
//     missing — AGENTS.md rule #23 spirit: never silently proceed).

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

vi.mock("server-only", () => ({}));

const mockCreateClient = vi.fn();

vi.mock("@supabase/supabase-js", () => ({
  createClient: (...args: unknown[]) => mockCreateClient(...args),
}));

import { getServiceRoleClient } from "../service-role";

const ORIGINAL_ENV = { ...process.env };

function resetEnv(): void {
  process.env = { ...ORIGINAL_ENV };
  delete process.env.SUPABASE_SERVICE_ROLE_KEY;
  delete process.env.NEXT_PUBLIC_SUPABASE_URL;
}

describe("getServiceRoleClient — env validation", () => {
  beforeEach(() => {
    resetEnv();
    mockCreateClient.mockReset();
    // Each successful createClient call returns a sentinel so we can
    // assert singleton behavior across calls.
    mockCreateClient.mockReturnValue({ __sentinel: true });
  });

  afterEach(() => {
    resetEnv();
    vi.clearAllMocks();
  });

  it("throws when SUPABASE_SERVICE_ROLE_KEY is missing (with the billing hint)", () => {
    process.env.NEXT_PUBLIC_SUPABASE_URL = "https://example.supabase.co";
    // SUPABASE_SERVICE_ROLE_KEY intentionally unset

    expect(() => getServiceRoleClient()).toThrow(/SUPABASE_SERVICE_ROLE_KEY/);
    expect(mockCreateClient).not.toHaveBeenCalled();
  });

  it("throws when NEXT_PUBLIC_SUPABASE_URL is missing (with the URL hint)", () => {
    process.env.SUPABASE_SERVICE_ROLE_KEY = "test-service-role-key";
    // NEXT_PUBLIC_SUPABASE_URL intentionally unset

    expect(() => getServiceRoleClient()).toThrow(/NEXT_PUBLIC_SUPABASE_URL/);
    expect(mockCreateClient).not.toHaveBeenCalled();
  });

  it("creates a Supabase client with the service-role key + URL when both are set", () => {
    process.env.NEXT_PUBLIC_SUPABASE_URL = "https://example.supabase.co";
    process.env.SUPABASE_SERVICE_ROLE_KEY = "test-service-role-key";

    const client = getServiceRoleClient();

    expect(mockCreateClient).toHaveBeenCalledTimes(1);
    expect(mockCreateClient).toHaveBeenCalledWith(
      "https://example.supabase.co",
      "test-service-role-key",
      expect.objectContaining({
        auth: expect.objectContaining({
          autoRefreshToken: false,
          persistSession: false,
        }),
      }),
    );
    expect(client).toEqual({ __sentinel: true });
  });

  it("returns the same singleton across multiple calls (no re-creation)", async () => {
    // Reset the module graph so the private `_serviceClient` slot
    // is fresh for THIS test (other tests in this file already warmed
    // it up by invoking getServiceRoleClient).
    vi.resetModules();
    const fresh = await import("../service-role");
    process.env.NEXT_PUBLIC_SUPABASE_URL = "https://example.supabase.co";
    process.env.SUPABASE_SERVICE_ROLE_KEY = "test-service-role-key";

    const a = fresh.getServiceRoleClient();
    const b = fresh.getServiceRoleClient();
    const c = fresh.getServiceRoleClient();

    expect(a).toBe(b);
    expect(b).toBe(c);
    // createClient must be invoked exactly once — the module caches
    // its result so the singleton survives across getServiceRoleClient
    // calls within one process.
    expect(mockCreateClient).toHaveBeenCalledTimes(1);
  });
});