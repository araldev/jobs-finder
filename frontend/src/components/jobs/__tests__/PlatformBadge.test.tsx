import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { PlatformBadge } from "../PlatformBadge";
import { renderWithIntl } from "@/test-utils";

describe("PlatformBadge", () => {
  it("renders platform name", () => {
    render(renderWithIntl(<PlatformBadge platform="linkedin" />, { locale: "es" }));
    expect(screen.getByText("LinkedIn")).toBeInTheDocument();
  });

  it("renders indeed", () => {
    render(renderWithIntl(<PlatformBadge platform="indeed" />, { locale: "es" }));
    expect(screen.getByText("Indeed")).toBeInTheDocument();
  });
});
