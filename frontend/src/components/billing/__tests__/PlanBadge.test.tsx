// Tests for PlanBadge — the header pill that shows the user's plan.
//
// The component renders the plan name from the Billing namespace
// translations. We mock next-intl's useTranslations to assert that
// the right key is read and the right display text is rendered.

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("server-only", () => ({}));

const mockTranslations: Record<string, string> = {
  "plans.free": "Free",
  "plans.pro": "Pro",
  "plans.proPlus": "Pro Plus",
};

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) =>
    mockTranslations[key] ?? `[missing:${key}]`,
}));

import { PlanBadge } from "../PlanBadge";

describe("PlanBadge — header plan pill", () => {
  it("renders 'Free' for the free plan", () => {
    render(<PlanBadge plan="free" />);
    expect(screen.getByText("Free")).toBeInTheDocument();
  });

  it("renders 'Pro' for the pro plan", () => {
    render(<PlanBadge plan="pro" />);
    expect(screen.getByText("Pro")).toBeInTheDocument();
  });

  it("renders 'Pro Plus' for the pro_plus plan (uses proPlus key)", () => {
    // The component branches to use plans.proPlus for pro_plus,
    // because the natural plans.pro_plus key isn't a valid
    // next-intl path segment. We assert the proPlus key is read.
    render(<PlanBadge plan="pro_plus" />);
    expect(screen.getByText("Pro Plus")).toBeInTheDocument();
  });

  it("renders exactly ONE badge per PlanBadge instance (no nested spinners)", () => {
    const { container } = render(<PlanBadge plan="pro" />);
    // The Badge primitive renders as a div with role=undefined —
    // we assert the text appears exactly once.
    expect(screen.getAllByText("Pro")).toHaveLength(1);
    expect(container.querySelectorAll("div")).toHaveLength(1);
  });
});