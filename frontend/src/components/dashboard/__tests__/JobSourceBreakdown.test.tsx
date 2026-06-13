import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { JobSourceBreakdown } from "../JobSourceBreakdown";
import type { ReactNode } from "react";

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        {children}
      </QueryClientProvider>
    );
  };
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("JobSourceBreakdown", () => {
  it("shows loading skeletons initially", () => {
    vi.mocked(fetch).mockImplementation(
      () =>
        new Promise(() => {
          /* never resolves — keep loading */
        }),
    );

    const { container } = render(<JobSourceBreakdown />, {
      wrapper: createWrapper(),
    });

    // Should render skeleton elements
    const skeletons = container.querySelectorAll(".animate-pulse");
    expect(skeletons.length).toBeGreaterThanOrEqual(3);
  });

  it("renders platform cards with data", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          total_jobs: 150,
          jobs_today: 5,
          active_platforms: 3,
          last_sync: "2026-06-13T10:00:00Z",
          platform_distribution: {
            linkedin: 80,
            indeed: 50,
            infojobs: 20,
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    render(<JobSourceBreakdown />, {
      wrapper: createWrapper(),
    });

    // Wait for data to load
    const linkedinLabel = await screen.findByText("LinkedIn");
    expect(linkedinLabel).toBeInTheDocument();

    expect(screen.getByText("Indeed")).toBeInTheDocument();
    expect(screen.getByText("InfoJobs")).toBeInTheDocument();

    // Counts should be visible
    expect(screen.getByText("80")).toBeInTheDocument();
    expect(screen.getByText("50")).toBeInTheDocument();
    expect(screen.getByText("20")).toBeInTheDocument();

    // Percentages
    expect(screen.getByText("53% of total")).toBeInTheDocument();
  });

  it("renders nothing on error", async () => {
    vi.mocked(fetch).mockRejectedValueOnce(new Error("Network error"));

    const { container } = render(<JobSourceBreakdown />, {
      wrapper: createWrapper(),
    });

    // Wait for the error state to resolve
    await vi.waitFor(() => {
      expect(container.textContent).toBe("");
    });
  });
});
