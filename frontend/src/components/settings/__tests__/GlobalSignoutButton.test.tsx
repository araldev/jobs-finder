import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { mockSupabaseAuth } from "@/lib/supabase/__mocks__/client";
import esMessages from "@/messages/es.json";
import { renderWithIntl } from "@/test-utils";

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => mockSupabaseAuth,
}));

const routerPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: routerPush, replace: vi.fn(), refresh: vi.fn() }),
}));

import { GlobalSignoutButton } from "../GlobalSignoutButton";

beforeEach(() => {
  vi.clearAllMocks();
  routerPush.mockClear();
});

describe("GlobalSignoutButton — REQ-AUTH-019 / REQ-AUTH-020", () => {
  it("renders the button with the Spanish trigger label", () => {
    render(renderWithIntl(<GlobalSignoutButton />, { locale: "es" }));
    expect(
      screen.getByRole("button", { name: esMessages.Auth.globalSignOut.triggerLabel }),
    ).toBeInTheDocument();
  });

  it("SCN-AUTH-019-2: documents the ~1h token-lifetime via muted helper text", () => {
    render(renderWithIntl(<GlobalSignoutButton />, { locale: "es" }));
    expect(screen.getByText(esMessages.Auth.globalSignOut.tooltip)).toBeInTheDocument();
  });

  it("SCN-AUTH-019-1: click → signOut({ scope: 'global' }) + router.push('/')", async () => {
    const user = userEvent.setup();
    render(renderWithIntl(<GlobalSignoutButton />, { locale: "es" }));

    await user.click(
      screen.getByRole("button", { name: esMessages.Auth.globalSignOut.triggerLabel }),
    );

    await waitFor(() => {
      expect(mockSupabaseAuth.auth.signOut).toHaveBeenCalledTimes(1);
    });
    expect(mockSupabaseAuth.auth.signOut).toHaveBeenCalledWith({ scope: "global" });
    await waitFor(() => {
      expect(routerPush).toHaveBeenCalledWith("/");
    });
  });
});
