import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import SearchLoading from "../loading";

describe("(app)/search/loading", () => {
  it("renders 9 skeleton cards in a grid with lg:grid-cols-2 xl:grid-cols-3 and h-[180px]", () => {
    const { container } = render(<SearchLoading />);

    // Grid container with the responsive column breakpoints that mirror
    // search/page.tsx:65-70 (prevents layout shift).
    const grid = container.querySelector(
      "div.grid.gap-4.lg\\:grid-cols-2.xl\\:grid-cols-3",
    );
    expect(grid).not.toBeNull();

    // Exactly 9 skeleton cards.
    const skeletons = grid?.querySelectorAll("div.h-\\[180px\\]");
    expect(skeletons?.length).toBe(9);

    // Each skeleton uses rounded-xl for visual consistency with the
    // search results grid.
    for (const skel of Array.from(skeletons ?? [])) {
      expect(skel.className).toContain("rounded-xl");
    }
  });
});
