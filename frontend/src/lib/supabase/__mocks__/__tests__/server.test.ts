import { describe, it, expect, vi } from "vitest";
import { createMockSupabaseServerClient } from "../server";

describe("createMockSupabaseServerClient", () => {
  it("returns a factory with every required method as a vi.fn()", () => {
    const mock = createMockSupabaseServerClient();

    const expectedMethods = [
      "exchangeCodeForSession",
      "getSession",
      "getUser",
    ] as const;

    for (const method of expectedMethods) {
      expect(vi.isMockFunction(mock.auth[method]), `${method} should be a vi.fn()`).toBe(true);
    }
  });

  it("exchangeCodeForSession resolves with the same default success shape", async () => {
    const mock = createMockSupabaseServerClient();
    const result = await mock.auth.exchangeCodeForSession("code");

    expect(result.error).toBeNull();
    expect(result.data?.user).toEqual({
      id: "user-1",
      email: "user@example.com",
      email_confirmed_at: null,
    });
  });

  it("getSession resolves with a null session default", async () => {
    const mock = createMockSupabaseServerClient();
    const result = await mock.auth.getSession();
    expect(result).toEqual({ data: { session: null }, error: null });
  });

  it("getUser resolves with the default user shape", async () => {
    const mock = createMockSupabaseServerClient();
    const result = await mock.auth.getUser();
    expect(result.data?.user).toEqual({
      id: "user-1",
      email: "user@example.com",
      email_confirmed_at: null,
    });
  });
});
