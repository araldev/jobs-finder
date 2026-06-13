import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { FavoriteButton } from "../FavoriteButton";
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
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("FavoriteButton", () => {
  it("renders outline heart when not favorited", () => {
    render(<FavoriteButton job={mockJob} />);
    const button = screen.getByRole("button");
    expect(button).toBeInTheDocument();
    expect(button).toHaveAttribute("aria-label", "Save to favorites");
    expect(button).toHaveAttribute("title", "Save to favorites");
  });

  it("renders filled heart when favorited", () => {
    render(<FavoriteButton job={mockJob} />);
    const button = screen.getByRole("button");

    // Click to favorite
    fireEvent.click(button);

    // After toggle, should show filled state
    expect(button).toHaveAttribute("aria-label", "Remove from favorites");
    expect(button).toHaveAttribute("title", "Remove from favorites");
  });

  it("click toggles state", () => {
    render(<FavoriteButton job={mockJob} />);
    const button = screen.getByRole("button");

    // Initially not favorited
    expect(button).toHaveAttribute("aria-label", "Save to favorites");

    // Click to favorite
    fireEvent.click(button);
    expect(button).toHaveAttribute("aria-label", "Remove from favorites");

    // Click again to unfavorite
    fireEvent.click(button);
    expect(button).toHaveAttribute("aria-label", "Save to favorites");
  });

  it("click does not propagate", () => {
    const parentClick = vi.fn();
    const { container } = render(
      <div onClick={parentClick}>
        <FavoriteButton job={mockJob} />
      </div>,
    );

    const button = container.querySelector("button")!;
    fireEvent.click(button);

    // Parent click should not fire
    expect(parentClick).not.toHaveBeenCalled();
  });
});
