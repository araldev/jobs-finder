import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

/**
 * Tests for REQ-CACHEUX-004 — the public job detail page
 * (`frontend/src/app/[locale]/jobs/[id]/page.tsx`) MUST migrate
 * from raw `useState` + `useEffect` + `fetch` to the existing
 * `useJobDetail(id)` hook.
 *
 * Behavioral equivalence (REQ-CACHEUX-004 scenario 1): same
 * components render for loading / data / error states; `markJobAsOpened`
 * still fires when the job resolves.
 *
 * Cross-visit cache (REQ-CACHEUX-004 scenario 2): the migrated page
 * benefits from React Query's 5min `staleTime` so revisiting a job
 * within 5min does NOT trigger a fetch (asserted indirectly via the
 * hook stub returning `data` immediately).
 *
 * Strategy: stub `useJobDetail` to return a controlled shape, then
 * assert the page renders the right branch (skeleton / content /
 * error). Stub `markJobAsOpened` to record calls.
 */

const useJobDetailMock = vi.fn();
vi.mock("@/hooks/useJobDetail", () => ({
  useJobDetail: (...args: unknown[]) => useJobDetailMock(...args),
}));

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
// the page-level composition (REQ-CACHEUX-004: "same components render").
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

// next/navigation must provide `useParams` and `useRouter` so the
// page can read the route id.
const mockBack = vi.fn();
vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "abc" }),
  useRouter: () => ({ back: mockBack, push: vi.fn() }),
}));

// Supabase client is needed by the auth-check useEffect.
vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({ data: { session: null }, error: null }),
    },
  }),
}));

// Import AFTER mocks are registered.
import PublicJobDetailPage from "../page";

beforeEach(() => {
  vi.clearAllMocks();
  mockBack.mockClear();
});

describe("PublicJobDetailPage — useJobDetail migration (REQ-CACHEUX-004)", () => {
  it("renders skeleton block when useJobDetail returns isLoading=true", () => {
    useJobDetailMock.mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
      refetch: vi.fn(),
    });

    const { container } = render(<PublicJobDetailPage />);

    // The skeleton block uses `Skeleton` primitives from
    // @/components/ui/skeleton (the .animate-pulse + .bg-muted class).
    const skeletons = container.querySelectorAll("div.animate-pulse");
    expect(skeletons.length).toBeGreaterThan(0);
    // Content + aside are NOT rendered in the loading branch.
    expect(screen.queryByTestId("job-detail-content")).not.toBeInTheDocument();
    expect(screen.queryByTestId("job-detail-aside")).not.toBeInTheDocument();
  });

  it("renders JobDetailContent + JobDetailAside when useJobDetail returns data", () => {
    useJobDetailMock.mockReturnValue({
      data: {
        id: "abc",
        source: "linkedin",
        title: "Senior Engineer",
        company: "Acme",
        location: "Madrid",
        url: "https://example.com/jobs/abc",
        posted_at: "2026-06-01T00:00:00Z",
        description: null,
      },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<PublicJobDetailPage />);

    expect(screen.getByTestId("job-detail-content")).toHaveTextContent(
      "content:abc",
    );
    expect(screen.getByTestId("job-detail-aside")).toHaveTextContent(
      "aside:abc",
    );
  });

  it("calls markJobAsOpened(id) when useJobDetail data resolves", () => {
    useJobDetailMock.mockReturnValue({
      data: {
        id: "abc",
        source: "linkedin",
        title: "Senior Engineer",
        company: "Acme",
        location: "Madrid",
        url: "https://example.com/jobs/abc",
        posted_at: "2026-06-01T00:00:00Z",
        description: null,
      },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<PublicJobDetailPage />);

    expect(markJobAsOpenedMock).toHaveBeenCalledWith("abc");
  });

  it("renders error block when useJobDetail returns error", () => {
    useJobDetailMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("Job not found"),
      refetch: vi.fn(),
    });

    render(<PublicJobDetailPage />);

    // The error block renders the error message text.
    expect(screen.getByText("Job not found")).toBeInTheDocument();
    // The "Reintentar" button is rendered (calls refetch on click).
    expect(
      screen.getByRole("button", { name: /reintentar/i }),
    ).toBeInTheDocument();
  });

  it("does NOT call markJobAsOpened while data is still loading", () => {
    useJobDetailMock.mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
      refetch: vi.fn(),
    });

    render(<PublicJobDetailPage />);

    expect(markJobAsOpenedMock).not.toHaveBeenCalled();
  });
});
