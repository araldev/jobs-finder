// Tests for CancellationBanner — the trial / canceling / canceled
// banners driven by the user's subscription state.
//
// The component renders an <Alert> only when the user is in one of
// the "at-risk" states (trialing + canceling, canceling before
// period end, or already canceled). A healthy subscription renders
// nothing.

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("server-only", () => ({}));

const mockTranslations: Record<string, string> = {
  "banners.canceled.title": "Subscription canceled",
  "banners.canceled.description":
    "Your Pro features are disabled. Reactivate from Settings.",
  "banners.trialCanceling.title": "Trial will not renew",
  "banners.trialCanceling.description":
    "Your Pro trial ends on {date}. You will be downgraded to Free.",
  "banners.canceling.title": "Subscription ends soon",
  "banners.canceling.description":
    "Your Pro subscription ends on {date}. Resubscribe to keep access.",
};

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string, params?: Record<string, unknown>) => {
    let text = mockTranslations[key] ?? `[missing:${key}]`;
    if (params?.date !== undefined) {
      text = text.replace("{date}", String(params.date));
    }
    return text;
  },
}));

import { CancellationBanner } from "../CancellationBanner";

describe("CancellationBanner — state-driven rendering", () => {
  it("renders nothing for an active subscription (no banner)", () => {
    const { container } = render(
      <CancellationBanner
        status="active"
        cancelAtPeriodEnd={false}
        currentPeriodEnd={null}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("renders the canceled banner when status='canceled'", () => {
    render(
      <CancellationBanner
        status="canceled"
        cancelAtPeriodEnd={false}
        currentPeriodEnd={null}
      />,
    );
    expect(
      screen.getByText("Subscription canceled"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Pro features are disabled/i),
    ).toBeInTheDocument();
  });

  it("renders the trial-canceling banner when status='trialing' + cancelAtPeriodEnd=true", () => {
    render(
      <CancellationBanner
        status="trialing"
        cancelAtPeriodEnd={true}
        currentPeriodEnd="2026-08-01T00:00:00.000Z"
      />,
    );
    expect(screen.getByText("Trial will not renew")).toBeInTheDocument();
    expect(
      screen.getByText(/Pro trial ends on/i),
    ).toBeInTheDocument();
  });

  it("renders the canceling banner when cancelAtPeriodEnd=true + currentPeriodEnd set (non-trialing)", () => {
    render(
      <CancellationBanner
        status="active"
        cancelAtPeriodEnd={true}
        currentPeriodEnd="2026-08-15T00:00:00.000Z"
      />,
    );
    expect(screen.getByText("Subscription ends soon")).toBeInTheDocument();
    expect(
      screen.getByText(/Pro subscription ends on/i),
    ).toBeInTheDocument();
  });

  it("does NOT render the canceling banner when currentPeriodEnd is null (no date to display)", () => {
    const { container } = render(
      <CancellationBanner
        status="active"
        cancelAtPeriodEnd={true}
        currentPeriodEnd={null}
      />,
    );
    // Without a currentPeriodEnd, the date placeholder would render
    // literally — we suppress that by returning null.
    expect(container).toBeEmptyDOMElement();
  });
});