import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

const usePathnameMock = vi.fn();
vi.mock("next/navigation", () => ({
  usePathname: () => usePathnameMock(),
}));

vi.mock("../ThemeToggle", () => ({
  ThemeToggle: () => null,
}));

vi.mock("@/components/auth/AuthStatus", () => ({
  AuthStatus: () => null,
}));

// Import after the mocks are registered.
import { Header } from "../Header";

describe("Header — page name resolution", () => {
  it.each([
    { path: "/dashboard", label: "Dashboard" },
    { path: "/search", label: "Search" },
    { path: "/favorites", label: "Favorites" },
    { path: "/settings", label: "Settings" },
    { path: "/jobs/abc-123", label: "Job Detail" },
  ])("route '$path' → heading '$label'", ({ path, label }) => {
    usePathnameMock.mockReturnValue(path);
    render(<Header />);
    // Get the FIRST <h1> in this render (test isolation via render).
    const h1 = document.querySelector("h1");
    expect(h1?.textContent).toContain(label);
  });

  it("unknown route → 'Jobs Finder' fallback (never 'JobsBoard')", () => {
    usePathnameMock.mockReturnValue("/totally-unknown");
    render(<Header />);
    const h1 = document.querySelector("h1");
    expect(h1?.textContent).toContain("Jobs Finder");
    expect(h1?.textContent).not.toContain("JobsBoard");
  });
});
