/**
 * Tests for REQ-PDPRSC-001 (provider-tree integrity) —
 * `(app)/layout.tsx` MUST NOT wrap its children in a second
 * `<Providers>` mount. Today it does, which causes:
 *
 *   - double `QueryClientProvider` mount (outer QueryClients
 *     don't dedup with inner ones — every `useQuery()` in the
 *     subtree hits the inner client and bypasses the outer
 *     cache);
 *   - double `ThemeProvider` mount (theme flash on remount);
 *   - double `Toaster` mount (duplicate toasts visible);
 *   - double `supabase.auth.getUser()` fetch on every dashboard
 *     mount (independent QueryClients don't dedup).
 *
 * The single mount already lives at `[locale]/layout.tsx:82`,
 * which wraps every `[locale]/*` route — including `(app)/*` —
 * so the `(app)` layout doesn't need its own.
 *
 * Test strategy: render `(app)/layout.tsx` inside an OUTER
 * `QueryClientProvider` that supplies a known-singleton client
 * (referenced by closure so we can `Object.is`-check). The
 * inner `Providers` (if present) would create its OWN
 * `QueryClient` and SHADOW the outer one — so a child calling
 * `useQueryClient()` returns the inner instance, NOT the outer
 * one. Removing the inner `<Providers>` causes the outer to win.
 *
 * `screen.getAllByTestId('sonner-toaster')` would not work
 * because sonner doesn't expose a `data-testid`; we query the
 * DOM directly via `aria-label="Notifications"` (sonner v2.0.7
 * renders the toast container as a `<section>` with
 * `aria-label="Notifications alt+T"`).
 *
 * We mock `AppShell` and `EmailVerificationBanner` (the two
 * non-trivial layout children) so the test exercises ONLY the
 * `<Providers>` wrapper contract. EmailVerificationBanner is
 * mocked because it calls `supabase.auth.getUser()` in
 * `useEffect`; AppShell because it pulls Sidebar + Header +
 * ChatDialog (all heavy client components with their own
 * contexts).
 */

import { describe, it, expect, vi } from "vitest";
import { render } from "@testing-library/react";
import {
  QueryClient,
  QueryClientProvider,
  useQueryClient,
} from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";

vi.mock("@/components/layout/AppShell", () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock("@/components/auth/EmailVerificationBanner", () => ({
  EmailVerificationBanner: () => null,
}));

import AppLayout from "../layout";

describe("(app)/layout — SCN-PDPRSC-001 (single Providers mount)", () => {
  it("SCN-PDPRSC-001-A: child useQueryClient() returns the OUTER QueryClient, not an inner one", () => {
    // The OUTER QueryClient is the one the [locale]/layout.tsx
    // already mounts. If (app)/layout.tsx adds a SECOND
    // `<Providers>` (with its own QueryClient), `useQueryClient()`
    // in the child subtree resolves to the INNER one — NOT this
    // outer one. The contract is: outer wins (no shadow).
    //
    // We deliberately wrap with `<QueryClientProvider>` directly
    // (NOT `<Providers>`) so the outer QueryClient is exactly
    // what the test holds in `outerQc`. The Toaster + ThemeProvider
    // in test 001-B are added by an explicit `<ThemeProvider>`
    // wrapper + a direct sonner `<Toaster />` mount, mirroring
    // what `<Providers>` does without instantiating a second
    // `QueryClient`.
    const outerQc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    let consumerQc: QueryClient | undefined;
    function Probe() {
      consumerQc = useQueryClient();
      return null;
    }

    render(
      <QueryClientProvider client={outerQc}>
        <AppLayout>
          <Probe />
        </AppLayout>
      </QueryClientProvider>,
    );

    expect(consumerQc).toBeDefined();
    // Object.is proves reference identity — a freshly-created
    // QueryClient inside the inner Providers would fail this
    // assertion.
    expect(Object.is(consumerQc, outerQc)).toBe(true);
  });

  it("SCN-PDPRSC-001-B: exactly one Toaster mounts in the DOM", () => {
    // sonner v2.0.7 renders the toast container as a `<section>`
    // with `aria-label="Notifications alt+T"` inside a Portal that
    // targets `document.body` (NOT the React container), so we
    // query document.body directly. @testing-library auto-cleans
    // `document.body` between tests, so a stale Toaster from a
    // prior test cannot pollute this count.
    //
    // If (app)/layout.tsx adds a second `<Providers>`, the
    // outer Toaster + the inner Toaster both mount → 2 sections.
    // Contract: exactly one.
    //
    // We mount an outer ThemeProvider + outer `<Toaster />` (the
    // two siblings Providers produces) WITHOUT a fresh QueryClient
    // — the outer QueryClientProvider above already supplies the
    // client. This mirrors what [locale]/layout.tsx does in
    // production: a single QueryClient + ThemeProvider + Toaster
    // chain that the (app)/layout MUST inherit, not duplicate.
    const outerQc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    const { Toaster } = require("sonner");
    // sonner's Toaster takes its theme from next-themes. The
    // outer ThemeProvider below provides that.
    render(
      <QueryClientProvider client={outerQc}>
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          enableSystem
          disableTransitionOnChange
        >
          <Toaster position="bottom-right" richColors closeButton />
          <AppLayout>
            <div data-testid="probe-child" />
          </AppLayout>
        </ThemeProvider>
      </QueryClientProvider>,
    );

    const toasters = document.body.querySelectorAll(
      'section[aria-label^="Notifications"]',
    );
    expect(toasters.length).toBe(1);
  });
});