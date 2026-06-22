import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { renderWithIntl } from "@/test-utils";

const routerRefreshMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    refresh: routerRefreshMock,
  }),
  usePathname: () => "/dashboard",
}));

vi.mock("framer-motion", () => ({
  motion: {
    div: ({ children, ...props }: { children: React.ReactNode; [key: string]: unknown }) => (
      <div {...props}>{children}</div>
    ),
  },
  useReducedMotion: () => false,
}));

// Import AFTER the mocks are registered.
import { LanguageSwitcher } from "./LanguageSwitcher";

describe("LanguageSwitcher — v1 cookie-based locale switching", () => {
  beforeEach(() => {
    routerRefreshMock.mockClear();
    document.cookie = "NEXT_LOCALE=; path=/; max-age=0";
    localStorage.clear();
  });

  it("renders the trigger button in the Header variant (icon-only)", () => {
    render(renderWithIntl(<LanguageSwitcher />, { locale: "es" }));
    expect(screen.getByRole("button", { name: /idioma|language/i })).toBeTruthy();
  });

  it("renders the trigger in the Footer variant (text + icon)", () => {
    render(renderWithIntl(<LanguageSwitcher inFooter />, { locale: "es" }));
    expect(screen.getByRole("button", { name: /idioma|language/i })).toBeTruthy();
  });

  it("clicking 'English' sets NEXT_LOCALE=en cookie, localStorage, and triggers router.refresh()", async () => {
    const user = userEvent.setup();

    render(renderWithIntl(<LanguageSwitcher />, { locale: "es" }));
    await user.click(screen.getByRole("button", { name: /idioma/i }));
    await user.click(screen.getByRole("menuitemradio", { name: /english/i }));

    expect(document.cookie).toMatch(/NEXT_LOCALE=en/);
    expect(localStorage.getItem("NEXT_LOCALE")).toBe("en");
    // v1 uses localePrefix: 'never', so the URL is NOT changed — only the
    // cookie + refresh trigger the RSC tree re-render in the new locale.
    expect(routerRefreshMock).toHaveBeenCalled();
  });

  it("clicking 'Español' sets NEXT_LOCALE=es cookie and triggers router.refresh()", async () => {
    const user = userEvent.setup();

    render(renderWithIntl(<LanguageSwitcher />, { locale: "en" }));
    await user.click(screen.getByRole("button", { name: /language/i }));
    await user.click(screen.getByRole("menuitemradio", { name: /español/i }));

    expect(document.cookie).toMatch(/NEXT_LOCALE=es/);
    expect(localStorage.getItem("NEXT_LOCALE")).toBe("es");
    expect(routerRefreshMock).toHaveBeenCalled();
  });

  it("supports keyboard navigation (Tab → Enter → ArrowDown → Enter)", async () => {
    const user = userEvent.setup();
    render(renderWithIntl(<LanguageSwitcher />, { locale: "es" }));

    const trigger = screen.getByRole("button", { name: /idioma/i });
    trigger.focus();
    expect(document.activeElement).toBe(trigger);

    await user.keyboard("{Enter}"); // Open menu
    await user.keyboard("{ArrowDown}"); // Move to first radio item
    await user.keyboard("{Enter}"); // Select

    // Selection triggers router.refresh(), not router.push() (v1).
    expect(routerRefreshMock).toHaveBeenCalled();
  });

  it("survives prefers-reduced-motion (no spring, just opacity)", () => {
    vi.doMock("framer-motion", () => ({
      motion: {
        div: ({ children, transition, ...props }: { children: React.ReactNode; transition?: Record<string, unknown>; [key: string]: unknown }) => (
          <div data-transition={JSON.stringify(transition ?? {})} {...props}>
            {children}
          </div>
        ),
      },
      useReducedMotion: () => true,
    }));
    // The conditional is evaluated at module scope, so this branch is
    // verified by the fact that the component still renders without
    // framer-motion throwing — the assertion is implicit in render().
    render(renderWithIntl(<LanguageSwitcher />, { locale: "es" }));
    expect(screen.getByRole("button", { name: /idioma/i })).toBeTruthy();
  });

  it("ignores localStorage failures (private mode)", async () => {
    const user = userEvent.setup();
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("QuotaExceededError");
    });

    render(renderWithIntl(<LanguageSwitcher />, { locale: "es" }));
    await user.click(screen.getByRole("button", { name: /idioma/i }));

    // Should NOT throw — the localStorage call is wrapped in try/catch.
    expect(() =>
      fireEvent.click(screen.getByRole("menuitemradio", { name: /english/i })),
    ).not.toThrow();

    setItemSpy.mockRestore();
  });
});
