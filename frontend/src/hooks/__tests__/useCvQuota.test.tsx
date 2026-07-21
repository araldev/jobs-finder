// Tests for the useCvQuota React Query hook.
//
// The hook fetches `/api/billing/cv-quota` once per stale window
// (60s). On a non-OK response it MUST fall back to a Free-shaped
// default so the dashboard counter doesn't break.

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { useCvQuota } from "../useCvQuota";
import type { CvQuotaResponse } from "@/types/billing";

function makeWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

describe("useCvQuota", () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    fetchSpy = vi.spyOn(globalThis, "fetch");
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  it("returns the quota shape on a 200 OK response", async () => {
    const payload: CvQuotaResponse = { used: 2, limit: 3, plan: "free" };
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => payload,
    } as Response);

    const { result } = renderHook(() => useCvQuota(), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual(payload);
    expect(fetchSpy).toHaveBeenCalledWith("/api/billing/cv-quota");
  });

  it("reports unlimited for a Pro user", async () => {
    const payload: CvQuotaResponse = {
      used: 12,
      limit: "unlimited",
      plan: "pro",
    };
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => payload,
    } as Response);

    const { result } = renderHook(() => useCvQuota(), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual(payload);
    expect(result.current.data?.limit).toBe("unlimited");
  });

  it("falls back to the Free default on a non-OK response", async () => {
    fetchSpy.mockResolvedValueOnce({
      ok: false,
      status: 503,
      json: async () => ({ error: "Billing is not enabled" }),
    } as Response);

    const { result } = renderHook(() => useCvQuota(), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    // The fallback matches Free: used=0, limit=3, plan=free.
    expect(result.current.data).toEqual({
      used: 0,
      limit: 3,
      plan: "free",
    });
  });

  it("falls back to the Free default on a 401 (unauthenticated)", async () => {
    fetchSpy.mockResolvedValueOnce({
      ok: false,
      status: 401,
      json: async () => ({ error: "Unauthorized" }),
    } as Response);

    const { result } = renderHook(() => useCvQuota(), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual({
      used: 0,
      limit: 3,
      plan: "free",
    });
  });
});