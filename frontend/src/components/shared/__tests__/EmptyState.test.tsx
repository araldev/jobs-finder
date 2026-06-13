import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { EmptyState } from "../EmptyState";

describe("EmptyState", () => {
  it("renders default empty variant", () => {
    render(<EmptyState />);
    expect(screen.getByText("Nothing here")).toBeInTheDocument();
  });

  it("renders no-results variant", () => {
    render(<EmptyState variant="no-results" />);
    expect(screen.getByText("No results found")).toBeInTheDocument();
  });

  it("renders no-jobs variant", () => {
    render(<EmptyState variant="no-jobs" />);
    expect(screen.getByText("No jobs yet")).toBeInTheDocument();
  });

  it("renders error variant", () => {
    render(<EmptyState variant="error" />);
    expect(screen.getByText("Something went wrong")).toBeInTheDocument();
  });

  it("renders custom title", () => {
    render(<EmptyState title="Custom Title" />);
    expect(screen.getByText("Custom Title")).toBeInTheDocument();
  });
});
