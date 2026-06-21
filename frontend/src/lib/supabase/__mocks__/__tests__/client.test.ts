import { describe, it, expect, vi, beforeEach } from "vitest";
import { createMockSupabaseAuth } from "../client";

describe("createMockSupabaseAuth", () => {
  beforeEach(() => {
    // The singleton accumulates call history across the whole file;
    // clear it between tests so per-test assertions about call counts
    // and `mockResolvedValueOnce` queueing are isolated.
    vi.clearAllMocks();
  });

  it("returns a factory with every required method as a vi.fn()", () => {
    const mock = createMockSupabaseAuth();

    const expectedMethods = [
      "resetPasswordForEmail",
      "updateUser",
      "resend",
      "signInWithOtp",
      "signOut",
      "getUser",
      "getSession",
      "exchangeCodeForSession",
      "onAuthStateChange",
    ] as const;

    for (const method of expectedMethods) {
      expect(vi.isMockFunction(mock.auth[method]), `${method} should be a vi.fn()`).toBe(true);
    }
  });

  it("exposes a top-level rpc spy", () => {
    const mock = createMockSupabaseAuth();
    expect(vi.isMockFunction(mock.rpc)).toBe(true);
  });

  it("resetPasswordForEmail resolves to a successful default shape", async () => {
    const mock = createMockSupabaseAuth();
    const result = await mock.auth.resetPasswordForEmail("user@example.com", {
      redirectTo: "http://localhost:3000/auth/callback?next=/reset-password",
    });

    expect(result).toEqual({
      data: { user: { id: "user-1", email: "user@example.com", email_confirmed_at: null } },
      error: null,
    });
  });

  it("updateUser resolves to a successful default shape", async () => {
    const mock = createMockSupabaseAuth();
    const result = await mock.auth.updateUser({ password: "new-password" });

    expect(result).toEqual({
      data: { user: { id: "user-1", email: "user@example.com", email_confirmed_at: null } },
      error: null,
    });
  });

  it("resend resolves to a successful default shape", async () => {
    const mock = createMockSupabaseAuth();
    const result = await mock.auth.resend({ type: "signup", email: "user@example.com" });

    expect(result).toEqual({
      data: { user: { id: "user-1", email: "user@example.com", email_confirmed_at: null } },
      error: null,
    });
  });

  it("signInWithOtp resolves to a successful default shape", async () => {
    const mock = createMockSupabaseAuth();
    const result = await mock.auth.signInWithOtp({ email: "user@example.com" });

    expect(result).toEqual({
      data: { user: { id: "user-1", email: "user@example.com", email_confirmed_at: null } },
      error: null,
    });
  });

  it("signOut resolves to a successful default shape", async () => {
    const mock = createMockSupabaseAuth();
    const result = await mock.auth.signOut();

    expect(result).toEqual({ error: null });
  });

  it("getUser resolves to a successful default shape", async () => {
    const mock = createMockSupabaseAuth();
    const result = await mock.auth.getUser();

    expect(result).toEqual({
      data: { user: { id: "user-1", email: "user@example.com", email_confirmed_at: null } },
      error: null,
    });
  });

  it("getSession resolves to a successful default shape", async () => {
    const mock = createMockSupabaseAuth();
    const result = await mock.auth.getSession();

    expect(result).toEqual({
      data: { session: null },
      error: null,
    });
  });

  it("exchangeCodeForSession resolves to a successful default shape", async () => {
    const mock = createMockSupabaseAuth();
    const result = await mock.auth.exchangeCodeForSession("auth-code");

    expect(result).toEqual({
      data: { user: { id: "user-1", email: "user@example.com", email_confirmed_at: null } },
      error: null,
    });
  });

  it("onAuthStateChange returns a no-op subscription", () => {
    const mock = createMockSupabaseAuth();
    const handle = mock.auth.onAuthStateChange(() => {});

    expect(handle).toEqual({
      data: {
        subscription: {
          unsubscribe: expect.any(Function) as () => void,
        },
      },
    });
    // Calling unsubscribe must not throw.
    handle.data.subscription.unsubscribe();
  });

  it("rpc resolves to a successful default shape with null data", async () => {
    const mock = createMockSupabaseAuth();
    const result = await mock.rpc("delete_current_user");

    expect(result).toEqual({ data: null, error: null });
  });

  it("every method can be overridden per-test (mockReturnValue)", async () => {
    const mock = createMockSupabaseAuth();
    const authError = new Error("Invalid login credentials");
    mock.auth.signInWithOtp.mockResolvedValueOnce({ data: null, error: authError });

    const result = await mock.auth.signInWithOtp({ email: "x@example.com" });
    expect(result.error).toBe(authError);
    expect(mock.auth.signInWithOtp).toHaveBeenCalledTimes(1);
  });

  it("rpc can be overridden per-test (mockResolvedValueOnce)", async () => {
    const mock = createMockSupabaseAuth();
    const rpcError = new Error("not authenticated");
    mock.rpc.mockResolvedValueOnce({ data: null, error: rpcError });

    const result = await mock.rpc("delete_current_user");
    expect(result.error).toBe(rpcError);
  });
});
