// Tests for the PlanCard — the settings-page card that shows the
// user's current plan + a manage CTA + an optional
// CancellationBanner slot.

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("server-only", () => ({}));

const mockTranslations: Record<string, string> = {
  "plans.free": "Free",
  "plans.pro": "Pro",
  "plans.proPlus": "Pro Plus",
  "labels.currentPlan": "Plan actual",
  "labels.cvLimit": "CVs por mes",
  "labels.savedLimit": "Búsquedas guardadas",
  "labels.notifications": "Notificaciones",
  "cta.upgrade": "Mejorar a Pro",
  "cta.manageSubscription": "Administrar suscripción",
  "cta.signInToUpgrade": "Iniciar sesión para actualizar",
  "values.unlimited": "Ilimitado",
  "values.disabled": "Desactivado",
  "values.enabled": "Activado",
};

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) =>
    mockTranslations[key] ?? `[missing:${key}]`,
}));

import { PlanCard } from "../PlanCard";

describe("PlanCard — settings summary", () => {
  it("renders the current plan name and 'Plan actual' label", () => {
    render(
      <PlanCard
        plan="pro"
        isAuthenticated={true}
        currentPeriodEnd="2026-08-01T00:00:00.000Z"
        cancelAtPeriodEnd={false}
        status="active"
      />,
    );
    expect(screen.getByText("Plan actual")).toBeInTheDocument();
    expect(screen.getByText("Pro")).toBeInTheDocument();
  });

  it("renders 'Ilimitado' for Pro's CV limit", () => {
    render(
      <PlanCard
        plan="pro"
        isAuthenticated={true}
        currentPeriodEnd={null}
        cancelAtPeriodEnd={false}
        status="active"
      />,
    );
    expect(screen.getByText("Ilimitado")).toBeInTheDocument();
  });

  it("renders the Free plan's numeric limits (3 CVs, 3 saved searches)", () => {
    render(
      <PlanCard
        plan="free"
        isAuthenticated={true}
        currentPeriodEnd={null}
        cancelAtPeriodEnd={false}
        status="active"
      />,
    );
    // The Free plan shows the literal numbers 3 / 3 in the rows.
    const rows = screen.getAllByText("3");
    expect(rows.length).toBeGreaterThanOrEqual(2);
  });

  it("renders the manage-subscription link for a paid user", () => {
    render(
      <PlanCard
        plan="pro"
        isAuthenticated={true}
        currentPeriodEnd={null}
        cancelAtPeriodEnd={false}
        status="active"
      />,
    );
    expect(
      screen.getByRole("link", { name: /Administrar suscripción/i }),
    ).toBeInTheDocument();
  });

  it("renders the sign-in CTA for an anonymous visitor", () => {
    render(
      <PlanCard
        plan="free"
        isAuthenticated={false}
        currentPeriodEnd={null}
        cancelAtPeriodEnd={false}
        status="active"
      />,
    );
    expect(
      screen.getByRole("link", { name: /Iniciar sesión/i }),
    ).toBeInTheDocument();
  });

  it("renders the CancellationBanner when status=canceled", () => {
    render(
      <PlanCard
        plan="pro"
        isAuthenticated={true}
        currentPeriodEnd={null}
        cancelAtPeriodEnd={false}
        status="canceled"
      />,
    );
    // The banner from the CancellationBanner component is rendered.
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });
});