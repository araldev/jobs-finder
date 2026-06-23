import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";

import { useCVAdapted } from "../useCVAdapted";

describe("useCVAdapted", () => {
  beforeEach(() => {
    vi.spyOn(globalThis, "fetch");
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("fetches the count from /api/cv/count on mount", async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ total_today: 3 }),
    } as Response);

    const { result } = renderHook(() => useCVAdapted());

    // Initial render: 0 (before fetch resolves)
    expect(result.current.cvAdaptedCount).toBe(0);

    // Wait for the fetch to resolve
    await waitFor(() => {
      expect(result.current.cvAdaptedCount).toBe(3);
    });

    expect(fetch).toHaveBeenCalledWith("/api/cv/count");
  });

  it("falls back to 0 when fetch fails", async () => {
    vi.mocked(fetch).mockRejectedValueOnce(new Error("Network error"));

    const { result } = renderHook(() => useCVAdapted());

    await vi.waitFor(() => {
      // Should stay at 0 with no error
      expect(result.current.cvAdaptedCount).toBe(0);
    });
  });

  it("falls back to 0 when backend returns non-ok", async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: false,
      status: 500,
    } as Response);

    const { result } = renderHook(() => useCVAdapted());

    await vi.waitFor(() => {
      expect(result.current.cvAdaptedCount).toBe(0);
    });
  });

  it("incrementCVAdapted bumps the count optimistically", async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ total_today: 2 }),
    } as Response);

    const { result } = renderHook(() => useCVAdapted());

    await waitFor(() => {
      expect(result.current.cvAdaptedCount).toBe(2);
    });

    act(() => {
      result.current.incrementCVAdapted();
    });

    expect(result.current.cvAdaptedCount).toBe(3);
  });

  it("does not set state after unmount (cancelled flag)", async () => {
    // Use a deferred promise so we control when it resolves
    let resolvePromise!: (data: { total_today: number }) => void;
    const deferred = new Promise<Response>((resolve) => {
      resolvePromise = (data: { total_today: number }) => {
        resolve({ ok: true, json: async () => data } as Response);
      };
    });
    vi.mocked(fetch).mockReturnValueOnce(deferred);

    const { result, unmount } = renderHook(() => useCVAdapted());

    // Unmount before the fetch resolves
    unmount();

    // Now resolve — this should not call setState on unmounted component
    await act(async () => {
      resolvePromise({ total_today: 99 });
    });

    // After unmount, state is never updated
    expect(result.current.cvAdaptedCount).toBe(0);
  });
});
