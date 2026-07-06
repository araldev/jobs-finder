import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { renderWithIntl } from "@/test-utils";
import type { Job } from "@/types/job";

// Mock `useFavorites` so the FavoriteButton tests don't depend on React
// Query's reactive cache (which has subtle timing issues under jsdom +
// React 19 batched re-renders). The optimistic-update logic itself is
// covered by `useFavorites.test.tsx` end-to-end. Here we only verify
// that the FavoriteButton reads `isFavorite` and calls `toggleFavorite`
// correctly — integration concerns are out of scope.
const mockUseFavorites = vi.fn();
vi.mock("@/hooks/useFavorites", () => ({
  useFavorites: () => mockUseFavorites(),
  FAVORITES_QUERY_KEY: ["favorites"],
}));

import { FavoriteButton } from "../FavoriteButton";

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
  mockUseFavorites.mockReset();
  // Default: not favorited, noop toggle/remove.
  mockUseFavorites.mockReturnValue({
    favorites: [],
    isFavorite: () => false,
    toggleFavorite: vi.fn(),
    removeFavorite: vi.fn(),
    favoriteCount: 0,
    isLoading: false,
    error: null,
  });
  // Localstorage stub (FavoriteButton doesn't touch it directly, but
  // the mocked useFavorites does via its internal helpers; harmless).
  const store = new Map<string, string>();
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(
    (key: string) => store.get(key) ?? null,
  );
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(
    (key: string, value: string) => { store.set(key, value); },
  );
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("FavoriteButton", () => {
  it("renders outline heart when not favorited", () => {
    render(renderWithIntl(<FavoriteButton job={mockJob} />, { locale: "es" }));
    const button = screen.getByRole("button");
    expect(button).toBeInTheDocument();
    expect(button).toHaveAttribute("aria-label", "Guardar en favoritos");
    expect(button).toHaveAttribute("title", "Guardar en favoritos");
  });

  it("renders filled heart when favorited", () => {
    mockUseFavorites.mockReturnValue({
      favorites: [mockJob],
      isFavorite: () => true,
      toggleFavorite: vi.fn(),
      removeFavorite: vi.fn(),
      favoriteCount: 1,
      isLoading: false,
      error: null,
    });
    render(renderWithIntl(<FavoriteButton job={mockJob} />, { locale: "es" }));
    const button = screen.getByRole("button");
    expect(button).toHaveAttribute("aria-label", "Quitar de favoritos");
    expect(button).toHaveAttribute("title", "Quitar de favoritos");
  });

  it("click calls toggleFavorite with the job", () => {
    const toggleFavorite = vi.fn();
    mockUseFavorites.mockReturnValue({
      favorites: [],
      isFavorite: () => false,
      toggleFavorite,
      removeFavorite: vi.fn(),
      favoriteCount: 0,
      isLoading: false,
      error: null,
    });
    render(renderWithIntl(<FavoriteButton job={mockJob} />, { locale: "es" }));
    const button = screen.getByRole("button");

    act(() => {
      fireEvent.click(button);
    });

    expect(toggleFavorite).toHaveBeenCalledWith(mockJob);
  });

  it("click does not propagate", () => {
    const parentClick = vi.fn();
    const { container } = render(
      <div onClick={parentClick}>
        {renderWithIntl(<FavoriteButton job={mockJob} />, { locale: "es" })}
      </div>,
    );

    const button = container.querySelector("button")!;
    fireEvent.click(button);

    expect(parentClick).not.toHaveBeenCalled();
  });
});