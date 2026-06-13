import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { PlatformBadge } from "../PlatformBadge";

describe("PlatformBadge", () => {
  it("renders platform name", () => {
    render(<PlatformBadge platform="linkedin" />);
    expect(screen.getByText("Linkedin")).toBeInTheDocument();
  });

  it("renders indeed", () => {
    render(<PlatformBadge platform="indeed" />);
    expect(screen.getByText("Indeed")).toBeInTheDocument();
  });
});
