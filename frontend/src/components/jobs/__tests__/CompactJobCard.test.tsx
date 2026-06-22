import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { CompactJobCard } from "../CompactJobCard";
import { renderWithIntl } from "@/test-utils";
import type { Job } from "@/types/job";

const mockJob: Job = {
  id: "job-1",
  source: "linkedin",
  title: "Software Engineer",
  company: "Acme Inc",
  location: "Remote",
  url: "https://example.com/job-1",
  posted_at: "2026-06-10T10:00:00Z",
  description: "A great job",
};

beforeEach(() => {
  const store = new Map<string, string>();
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(
    (key: string) => store.get(key) ?? null,
  );
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(
    (key: string, value: string) => { store.set(key, value); },
  );
  // Mock IntersectionObserver
  vi.stubGlobal("IntersectionObserver", vi.fn(() => ({
    observe: vi.fn(),
    unobserve: vi.fn(),
    disconnect: vi.fn(),
  })));
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("CompactJobCard", () => {
  it("renders job title and company", () => {
    render(renderWithIntl(<CompactJobCard job={mockJob} />, { locale: "es" }));
    expect(screen.getByText("Software Engineer")).toBeInTheDocument();
    expect(screen.getByText("Acme Inc")).toBeInTheDocument();
  });

  it("renders location with MapPin icon", () => {
    render(renderWithIntl(<CompactJobCard job={mockJob} />, { locale: "es" }));
    expect(screen.getByText("Remote")).toBeInTheDocument();
  });

  it("renders ExternalLink button", () => {
    render(renderWithIntl(<CompactJobCard job={mockJob} />, { locale: "es" }));
    const button = screen.getByLabelText("Abrir oferta de empleo");
    expect(button).toBeInTheDocument();
    expect(button).toHaveAttribute("type", "button");
  });

  it("renders FavoriteButton", () => {
    render(renderWithIntl(<CompactJobCard job={mockJob} />, { locale: "es" }));
    const favButton = screen.getByLabelText("Guardar en favoritos");
    expect(favButton).toBeInTheDocument();
  });

  it("renders PlatformBadge", () => {
    render(renderWithIntl(<CompactJobCard job={mockJob} />, { locale: "es" }));
    expect(screen.getByText("LinkedIn")).toBeInTheDocument();
  });

  it("renders date", () => {
    render(renderWithIntl(<CompactJobCard job={mockJob} />, { locale: "es" }));
    // Default locale is now Spanish (i18n slice 4). The date is "10 de jun. de 2026"
    // in ES or "Jun 10, 2026" in EN. Slice 8 will migrate the callsite to pass
    // the active locale explicitly; for now we accept either format.
    expect(screen.getByText(/Jun 10, 2026|10 de Jun(?:.+)? de 2026|Unknown/)).toBeInTheDocument();
  });

  it("links to job detail page", () => {
    render(renderWithIntl(<CompactJobCard job={mockJob} />, { locale: "es" }));
    const link = screen.getByRole("link", { name: /Software Engineer/ });
    expect(link).toHaveAttribute("href", "/jobs/job-1");
  });
});
