import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import AuthLayout from "../layout";

describe("(auth)/layout — public auth shell", () => {
  it("renders the brand link to '/' with the logo image", () => {
    render(
      <AuthLayout>
        <div data-testid="child">child content</div>
      </AuthLayout>,
    );

    const link = screen.getByRole("link", { name: /jobs finder/i });
    expect(link).toHaveAttribute("href", "/");
    // The child content is rendered inside the card.
    expect(screen.getByTestId("child")).toBeInTheDocument();
  });

  it("logo image uses next/image (loading='lazy' + width + height set)", () => {
    // next/image sets `loading="lazy"` and explicit width/height on the
    // underlying <img>. A raw <img> tag would not. This guards against
    // a future regression to a plain <img> tag (AGENTS rule #13 +
    // next/core-web-vitals/@next/next/no-img-element).
    const { container } = render(
      <AuthLayout>
        <span>x</span>
      </AuthLayout>,
    );
    const img = container.querySelector("img");
    expect(img).not.toBeNull();
    expect(img).toHaveAttribute("alt", "Jobs Finder");
    expect(img).toHaveAttribute("loading", "lazy");
    // next/image always sets width/height attributes (numeric, not CSS).
    const width = img?.getAttribute("width");
    const height = img?.getAttribute("height");
    expect(width).toBeTruthy();
    expect(height).toBeTruthy();
  });
});
