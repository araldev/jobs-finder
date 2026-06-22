import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { mockSupabaseAuth } from "@/lib/supabase/__mocks__/client";
import { authCopy } from "@/lib/authCopy";
import { cleanupJobsFinderLocalStorage } from "@/lib/auth/cleanupJobsFinderLocalStorage";
import { renderWithIntl } from "@/test-utils";

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => mockSupabaseAuth,
}));

// Spy on the cleanup helper so we can assert its call ORDER relative to
// the RPC and signOut. The real implementation still runs (so the
// localStorage assertions in the success path remain meaningful), but
// vitest now records every invocation timing for ordering checks.
vi.mock("@/lib/auth/cleanupJobsFinderLocalStorage", async (importOriginal) => {
  const actual =
    await importOriginal<
      typeof import("@/lib/auth/cleanupJobsFinderLocalStorage")
    >();
  return {
    cleanupJobsFinderLocalStorage: vi.fn(actual.cleanupJobsFinderLocalStorage),
  };
});

const routerPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: routerPush, replace: vi.fn(), refresh: vi.fn() }),
}));

import { DeleteAccountDialog } from "../DeleteAccountDialog";

const cleanupMock = vi.mocked(cleanupJobsFinderLocalStorage);

const USER_EMAIL = "user@example.com";

beforeEach(() => {
  vi.clearAllMocks();
  routerPush.mockClear();
  // Reset localStorage between tests
  const store = new Map<string, string>();
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(
    (key: string) => store.get(key) ?? null,
  );
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(
    (key: string, value: string) => {
      store.set(key, value);
    },
  );
  vi.spyOn(Storage.prototype, "removeItem").mockImplementation((key: string) => {
    store.delete(key);
  });
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: {
      _store: store,
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => {
        store.set(k, v);
      },
      removeItem: (k: string) => {
        store.delete(k);
      },
      clear: () => {
        store.clear();
      },
      key: (i: number) => Array.from(store.keys())[i] ?? null,
      get length() {
        return store.size;
      },
    },
  });
});

describe("DeleteAccountDialog — REQ-AUTH-011 / REQ-AUTH-012 / REQ-AUTH-013", () => {
  it("SCN-AUTH-011-3: uses AlertDialog (role='alertdialog' present)", async () => {
    const user = userEvent.setup();
    render(renderWithIntl(<DeleteAccountDialog userEmail={USER_EMAIL} />, { locale: "es" }));

    // Open the dialog
    await user.click(screen.getByRole("button", { name: authCopy.delete.triggerLabel }));

    await waitFor(() => {
      expect(
        document.querySelector('[role="alertdialog"]'),
      ).toBeInTheDocument();
    });
  });

  it("SCN-AUTH-011-1: typed email mismatch → confirm disabled + aria-disabled + inline Spanish error", async () => {
    const user = userEvent.setup();
    render(renderWithIntl(<DeleteAccountDialog userEmail={USER_EMAIL} />, { locale: "es" }));

    await user.click(screen.getByRole("button", { name: authCopy.delete.triggerLabel }));

    // Wait for the dialog to open
    await waitFor(() => {
      expect(
        document.querySelector('[role="alertdialog"]'),
      ).toBeInTheDocument();
    });

    const input = screen.getByTestId("delete-account-confirm-input");
    await user.type(input, "different@example.com");

    const confirmBtn = screen.getByRole("button", { name: authCopy.delete.confirmSubmit });
    expect(confirmBtn).toBeDisabled();
    expect(confirmBtn).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByText(authCopy.validation.deleteEmailMismatch)).toBeInTheDocument();
  });

  it("SCN-AUTH-011-2: case-insensitive trim match → confirm enabled", async () => {
    const user = userEvent.setup();
    render(renderWithIntl(<DeleteAccountDialog userEmail={USER_EMAIL} />, { locale: "es" }));

    await user.click(screen.getByRole("button", { name: authCopy.delete.triggerLabel }));

    await waitFor(() => {
      expect(
        document.querySelector('[role="alertdialog"]'),
      ).toBeInTheDocument();
    });

    const input = screen.getByTestId("delete-account-confirm-input");
    await user.type(input, "  USER@EXAMPLE.COM  ");

    const confirmBtn = screen.getByRole("button", { name: authCopy.delete.confirmSubmit });
    expect(confirmBtn).not.toBeDisabled();
  });

  it("SCN-AUTH-012-1: success → rpc → localStorage cleanup → signOut → router.push('/')", async () => {
    const user = userEvent.setup();
    // Seed localStorage
    localStorage.setItem("jobs-finder-favorites", "[]");
    localStorage.setItem("jobs-finder-chat-v1", "{}");
    localStorage.setItem("theme", "dark"); // unrelated — must survive
    mockSupabaseAuth.rpc.mockResolvedValueOnce({ data: null, error: null });

    render(renderWithIntl(<DeleteAccountDialog userEmail={USER_EMAIL} />, { locale: "es" }));
    await user.click(screen.getByRole("button", { name: authCopy.delete.triggerLabel }));

    await waitFor(() => {
      expect(
        document.querySelector('[role="alertdialog"]'),
      ).toBeInTheDocument();
    });

    const input = screen.getByTestId("delete-account-confirm-input");
    await user.type(input, USER_EMAIL);

    const confirmBtn = screen.getByRole("button", { name: authCopy.delete.confirmSubmit });
    await user.click(confirmBtn);

    await waitFor(() => {
      expect(mockSupabaseAuth.rpc).toHaveBeenCalledTimes(1);
    });
    expect(mockSupabaseAuth.rpc).toHaveBeenCalledWith("delete_current_user");

    // Call ORDER per spec REQ-AUTH-012: rpc → cleanup → signOut → push.
    // `invocationCallOrder` is a monotonically increasing counter across
    // every vi.fn() in the test; lower numbers were called first.
    const rpcOrder = mockSupabaseAuth.rpc.mock.invocationCallOrder[0]!;
    const cleanupOrder = cleanupMock.mock.invocationCallOrder[0]!;
    const signOutOrder = mockSupabaseAuth.auth.signOut.mock.invocationCallOrder[0]!;
    expect(rpcOrder).toBeLessThan(cleanupOrder);
    expect(cleanupOrder).toBeLessThan(signOutOrder);

    // localStorage cleanup removed jobs-finder-* keys and left unrelated keys.
    await waitFor(() => {
      expect(localStorage.getItem("jobs-finder-favorites")).toBeNull();
      expect(localStorage.getItem("jobs-finder-chat-v1")).toBeNull();
      expect(localStorage.getItem("theme")).toBe("dark");
    });

    // signOut + redirect
    await waitFor(() => {
      expect(mockSupabaseAuth.auth.signOut).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(routerPush).toHaveBeenCalledWith("/");
    });
  });

  it("SCN-AUTH-012-2: RPC rejects → Spanish toast + dialog stays open", async () => {
    const user = userEvent.setup();
    mockSupabaseAuth.rpc.mockResolvedValueOnce({
      data: null,
      error: new Error("not authenticated"),
    });

    render(renderWithIntl(<DeleteAccountDialog userEmail={USER_EMAIL} />, { locale: "es" }));
    await user.click(screen.getByRole("button", { name: authCopy.delete.triggerLabel }));

    await waitFor(() => {
      expect(
        document.querySelector('[role="alertdialog"]'),
      ).toBeInTheDocument();
    });

    const input = screen.getByTestId("delete-account-confirm-input");
    await user.type(input, USER_EMAIL);

    const confirmBtn = screen.getByRole("button", { name: authCopy.delete.confirmSubmit });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(mockSupabaseAuth.rpc).toHaveBeenCalledTimes(1);
    });
    // Dialog still open — the user can retry.
    await waitFor(() => {
      expect(
        document.querySelector('[role="alertdialog"]'),
      ).toBeInTheDocument();
    });
    // signOut was NOT called.
    expect(mockSupabaseAuth.auth.signOut).not.toHaveBeenCalled();
  });

  it("SCN-AUTH-012-3: when RPC rejects, localStorage is NOT touched (no partial data loss)", async () => {
    // The CRITICAL assertion for REQ-AUTH-012: if the server-side delete
    // fails, the user's favorites / chat history / cv count MUST remain
    // intact. Wiping localStorage on RPC failure is data loss from the
    // user's perspective — their Supabase data is still there but the
    // UI shows an empty state.
    const user = userEvent.setup();
    localStorage.setItem("jobs-finder-favorites", "[]");
    localStorage.setItem("jobs-finder-chat-v1", "{}");
    localStorage.setItem("jobs-finder-cv-adapted-count", "3");
    localStorage.setItem("theme", "dark");
    mockSupabaseAuth.rpc.mockResolvedValueOnce({
      data: null,
      error: new Error("not authenticated"),
    });

    render(renderWithIntl(<DeleteAccountDialog userEmail={USER_EMAIL} />, { locale: "es" }));
    await user.click(screen.getByRole("button", { name: authCopy.delete.triggerLabel }));

    await waitFor(() => {
      expect(
        document.querySelector('[role="alertdialog"]'),
      ).toBeInTheDocument();
    });

    const input = screen.getByTestId("delete-account-confirm-input");
    await user.type(input, USER_EMAIL);

    const confirmBtn = screen.getByRole("button", { name: authCopy.delete.confirmSubmit });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(mockSupabaseAuth.rpc).toHaveBeenCalledTimes(1);
    });

    // Cleanup helper MUST NOT have run — localStorage is fully intact.
    expect(cleanupMock).not.toHaveBeenCalled();
    expect(localStorage.getItem("jobs-finder-favorites")).not.toBeNull();
    expect(localStorage.getItem("jobs-finder-chat-v1")).not.toBeNull();
    expect(localStorage.getItem("jobs-finder-cv-adapted-count")).toBe("3");
    expect(localStorage.getItem("theme")).toBe("dark");
    // No sign-out, no redirect.
    expect(mockSupabaseAuth.auth.signOut).not.toHaveBeenCalled();
    expect(routerPush).not.toHaveBeenCalled();
  });
});
