import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import type { Job } from "@/types/job";

/**
 * Tests for REQ-CACHEUX-004 — second scenario (Cross-visit cache).
 *
 * Closes WARNING-1 from verify-report #603/#604 of the parent
 * `perf-frontend-cache-ux` change. The sibling file `page.test.tsx`
 * mocks `@/hooks/useJobDetail` at module scope (line 25-27), so the
 * REAL React Query cache is never exercised by those 5 equivalence
 * tests. The cross-visit behavior is only asserted indirectly through
 * the stub.
 *
 * This sibling file does NOT mock `useJobDetail` — it lets the real
 * hook run, pre-seeds the React Query cache for `["jobs", "abc"]`,
 * and asserts that NO fetch fires to `/api/jobs/abc` because the
 * cache is fresh (within the 5min `staleTime` configured in
 * `providers.tsx:14`).
 *
 * Why a sibling file and not a new `describe` in `page.test.tsx`:
 * vitest hoists `vi.mock()` to the top of the test MODULE, and that
 * hoisted mock is scoped to the test file. Adding a `describe` to
 * `page.test.tsx` would inherit the module-scoped
 * `vi.mock('@/hooks/useJobDetail')` and the new test would never
 * hit the real hook.
 */

const markJobAsOpenedMock = vi.fn();
vi.mock("@/lib/chat-storage", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/chat-storage")>(
      "@/lib/chat-storage",
    );
  return {
    ...actual,
    markJobAsOpened: (...args: unknown[]) => markJobAsOpenedMock(...args),
    useOpenedJobs: () => new Set<string>(),
  };
});

// Stub the components that the page renders so the test focuses on
// the page-level composition + the real React Query cache behavior.
vi.mock("@/components/jobs/JobDetailContent", () => ({
  JobDetailContent: ({ job }: { job: { id: string } }) => (
    <div data-testid="job-detail-content">content:{job.id}</div>
  ),
}));
vi.mock("@/components/jobs/JobDetailAside", () => ({
  JobDetailAside: ({ job }: { job: { id: string } }) => (
    <div data-testid="job-detail-aside">aside:{job.id}</div>
  ),
}));
vi.mock("@/components/chat/ChatDialog", () => ({
  ChatDialog: () => <div data-testid="chat-dialog-sentinel" />,
}));
vi.mock("@/components/layout/Footer", () => ({
  Footer: () => <div data-testid="footer-sentinel" />,
}));

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "abc" }),
  useRouter: () => ({ back: vi.fn(), push: vi.fn() }),
}));

// The page uses the shared Header component — mock it to avoid
// next/navigation + React Query dependencies in this test.
vi.mock("@/components/layout/Header", () => ({
  Header: () => null,
}));

// Mock useTranslations so the page doesn't need NextIntlClientProvider.
vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}));

// NOTE: @/hooks/useJobDetail is INTENTIONALLY NOT mocked here. The
// real hook must run so that React Query's cache is exercised.

// Import AFTER all `vi.mock()` calls so the mocks are registered
// before the page module is evaluated.
import PublicJobDetailPage from "../page";

const jobFixture: Job = {
  id: "abc",
  source: "linkedin",
  title: "Senior Engineer",
  company: "Acme",
  location: "Madrid",
  url: "https://example.com/jobs/abc",
  posted_at: "2026-06-01T00:00:00Z",
  description: null,
};

describe("PublicJobDetailPage — cross-visit cache (REQ-CACHEUX-004 scenario 2)", () => {
  let queryClient: QueryClient;
  let fetchSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    // Fresh QueryClient per test, matching the 5min staleTime
    // configured in providers.tsx:14 so a pre-seeded entry is
    // considered fresh and the queryFn is never invoked.
    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          staleTime: 5 * 60 * 1000,
          retry: false,
        },
      },
    });
    // Pre-seed the cache for the queryKey used in useJobDetail.ts:8.
    queryClient.setQueryData(["jobs", "abc"], jobFixture);
    // Spy on globalThis.fetch for OBSERVATION (we assert zero
    // matching calls). The mockResolvedValue is a safety net in
    // case anything accidentally hits the network — we want the
    // test to complete rather than hang on a real fetch.
    fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response("{}", { status: 200 }));
    vi.clearAllMocks();
    // Re-establish the spy after clearAllMocks (which clears the
    // mock's call history but does NOT restore the implementation).
    // The spy still has the mockResolvedValue; the call history is
    // now empty for this test.
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("does NOT fetch /api/jobs/abc when the React Query cache is pre-seeded", () => {
    render(<PublicJobDetailPage />, {
      wrapper: ({ children }: { children: ReactNode }) => (
        <QueryClientProvider client={queryClient}>
          {children}
        </QueryClientProvider>
      ),
    });

    // (a) Pre-seeded Job renders via the real useJobDetail hook
    //     (proves the cache was hit, not a loading skeleton).
    expect(screen.getByTestId("job-detail-content")).toHaveTextContent(
      "content:abc",
    );
    // (b) markJobAsOpened side-effect fires (proves the page
    //     committed with the pre-seeded data, not a loading skeleton).
    expect(markJobAsOpenedMock).toHaveBeenCalledWith("abc");
    // (c) NO fetch fired for the job detail endpoint — the React
    //     Query cache short-circuited the queryFn. Filter on
    //     `/api/jobs/abc` substring only (per #608 risk table:
    //     `/_next/...` and favicon would over-match a broader
    //     pattern).
    expect(
      fetchSpy.mock.calls.every(
        (call: Parameters<typeof fetch>) =>
          !String(call[0]).includes("/api/jobs/abc"),
      ),
    ).toBe(true);
  });
});
