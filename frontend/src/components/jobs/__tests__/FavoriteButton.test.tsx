import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { FavoriteButton } from "../FavoriteButton";
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
    render(renderWithIntl(<FavoriteButton job={mockJob} />, { locale: "es" }));
    const button = screen.getByRole("button");

    fireEvent.click(button);

    expect(button).toHaveAttribute("aria-label", "Quitar de favoritos");
    expect(button).toHaveAttribute("title", "Quitar de favoritos");
  });

  it("click toggles state", () => {
    render(renderWithIntl(<FavoriteButton job={mockJob} />, { locale: "es" }));
    const button = screen.getByRole("button");

    expect(button).toHaveAttribute("aria-label", "Guardar en favoritos");

    fireEvent.click(button);
    expect(button).toHaveAttribute("aria-label", "Quitar de favoritos");

    fireEvent.click(button);
    expect(button).toHaveAttribute("aria-label", "Guardar en favoritos");
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
