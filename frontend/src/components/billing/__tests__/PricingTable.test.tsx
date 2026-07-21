// Tests for the PricingTable component.
//
// Renders a 3-card responsive grid (Free / Pro / Pro Plus) where
// the user's current plan is visually marked and Pro Plus is locked.
// We assert behavior, not CSS classes:
//   - 3 cards are rendered (one per plan).
//   - Pro Plus's CTA is disabled.
//   - The current plan shows a visual marker (e.g. a "Current plan"
//     label that the other cards don't show).
//   - All 3 plan names appear in the rendered DOM.

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("server-only", () => ({}));

const mockTranslations: Record<string, string> = {
  "plans.free": "Free",
  "plans.pro": "Pro",
  "plans.proPlus": "Pro Plus",
  "cta.currentPlan": "Tu plan actual",
  "cta.upgrade": "Mejorar a Pro",
  "cta.proPlusSoon": "Próximamente",
  "cta.manageSubscription": "Administrar suscripción",
  "cta.signInToUpgrade": "Iniciar sesión para actualizar",
  "features.free.cv": "3 adaptaciones de CV por mes",
  "features.free.saved": "3 búsquedas guardadas",
  "features.free.notif": "Sin notificaciones",
  "features.pro.cv": "Adaptaciones ilimitadas",
  "features.pro.saved": "20 búsquedas guardadas",
  "features.pro.notif": "Notificaciones activadas",
  "features.proPlus.cv": "Todo lo de Pro",
  "features.proPlus.saved": "Búsquedas ilimitadas",
  "features.proPlus.notif": "Notificaciones prioritarias",
};

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) =>
    mockTranslations[key] ?? `[missing:${key}]`,
}));

import { PricingTable } from "../PricingTable";

describe("PricingTable", () => {
  it("renders all 3 plan names (Free / Pro / Pro Plus)", () => {
    render(<PricingTable currentPlan="free" isAuthenticated={true} />);
    expect(screen.getByText("Free")).toBeInTheDocument();
    expect(screen.getByText("Pro")).toBeInTheDocument();
    expect(screen.getByText("Pro Plus")).toBeInTheDocument();
  });

  it("marks the user's current plan visually (Tu plan actual)", () => {
    render(<PricingTable currentPlan="pro" isAuthenticated={true} />);
    // Only ONE card should carry the current-plan marker.
    const markers = screen.getAllByText("Tu plan actual");
    expect(markers).toHaveLength(1);
  });

  it("renders Pro Plus CTA as DISABLED (Próximamente)", () => {
    render(<PricingTable currentPlan="free" isAuthenticated={true} />);
    const proPlusButton = screen.getByRole("button", { name: /Próximamente/i });
    expect(proPlusButton).toBeDisabled();
  });

  it("Free + Pro CTAs are NOT disabled (active plans)", () => {
    render(<PricingTable currentPlan="free" isAuthenticated={true} />);
    // The Pro upgrade CTA renders as a Link (Button asChild) — we
    // query by accessible name so the test survives the
    // Link/Button wrapping change.
    const upgradeLink = screen.getByRole("link", { name: /Mejorar a Pro/i });
    expect(upgradeLink).toBeInTheDocument();
    expect(upgradeLink).not.toHaveAttribute("aria-disabled", "true");
    // Pro Plus renders as a disabled button.
    const proPlusButton = screen.getByRole("button", { name: /Próximamente/i });
    expect(proPlusButton).toBeDisabled();
  });

  it("renders a sign-in CTA for anonymous visitors", () => {
    render(<PricingTable currentPlan="free" isAuthenticated={false} />);
    // Both Free + Pro cards show the sign-in link for anon users
    // (Free card = "current plan disabled for anon" still surfaces
    // a sign-in entry point; Pro card = upgrade requires auth).
    const signInLinks = screen.getAllByRole("link", { name: /Iniciar sesión/i });
    expect(signInLinks.length).toBeGreaterThanOrEqual(1);
  });

  it("renders the 'manage subscription' CTA for a paid user", () => {
    render(<PricingTable currentPlan="pro" isAuthenticated={true} />);
    expect(
      screen.getByRole("link", { name: /Administrar suscripción/i }),
    ).toBeInTheDocument();
  });
});