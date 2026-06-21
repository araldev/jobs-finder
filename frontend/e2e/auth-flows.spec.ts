/**
 * Playwright E2E happy paths for the auth-flows change.
 *
 * Tagged `@manual-smoke` — these tests are NOT part of CI (per AGENTS
 * convention 1: no live Supabase email delivery in tests). Run
 * manually against a local stack:
 *
 *   # Terminal 1: local Supabase stack with Inbucket mail preview
 *   cd backend && supabase start
 *
 *   # Terminal 2: backend scraper
 *   cd backend && uv run uvicorn jobs_finder.main:app --reload
 *
 *   # Terminal 3: Next.js dev
 *   cd frontend && npm run dev
 *
 *   # Terminal 4: the spec
 *   cd frontend && npx playwright test e2e/auth-flows.spec.ts
 *
 * Inbucket previews the recovery / magic-link emails at
 * http://localhost:54324 — each test fetches the latest email and
 * clicks the embedded link to land on /reset-password or /dashboard.
 *
 * Tests covered (from spec #512):
 *   A — Password reset (REQ-AUTH-001..004)
 *   E — Magic-link / OTP login (REQ-AUTH-017)
 *   C — Account deletion (REQ-AUTH-009..013)
 */

import { test, expect, type Page } from "@playwright/test";

const INBUCKET_URL = process.env.INBUCKET_URL ?? "http://localhost:54324";
const APP_URL = process.env.E2E_BASE_URL ?? "http://localhost:3000";

/**
 * Wait for a new email to appear in Inbucket matching `emailFilter`,
 * then return its HTML body (decoded from the multipart/alternative
 * payload — Inbucket's `/api/v1/mailbox/<addr>/<id>` returns the raw
 * MIME; we extract the text/html part).
 */
async function fetchLatestEmail(
  emailFilter: (subject: string) => boolean,
): Promise<{ subject: string; html: string }> {
  // Poll the Inbucket listing endpoint.
  const listUrl = `${INBUCKET_URL}/api/v1/mailbox/dev@supabase.local`;
  // Wait up to 30s for a matching email.
  const deadline = Date.now() + 30_000;
  let emailId: string | null = null;
  let subject = "";
  while (Date.now() < deadline) {
    const res = await fetch(listUrl);
    if (res.ok) {
      const list = (await res.json()) as Array<{ id: string; subject: string }>;
      const match = list.find((m) => emailFilter(m.subject));
      if (match) {
        emailId = match.id;
        subject = match.subject;
        break;
      }
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  if (!emailId) {
    throw new Error(`No email matching filter arrived at ${INBUCKET_URL} within 30s`);
  }

  const body = await fetch(`${listUrl}/${emailId}`);
  const json = (await body.json()) as { body: { html?: string } };
  return { subject, html: json.body?.html ?? "" };
}

/** Extract the first href from an HTML email body. */
function firstHref(html: string): string {
  const match = html.match(/href=["']([^"']+)["']/i);
  if (!match) throw new Error(`No href found in email body: ${html.slice(0, 200)}`);
  return match[1] as string;
}

// ---------------------------------------------------------------------------
// A — Password reset happy path (SCN-AUTH-001..004)
// ---------------------------------------------------------------------------

test.describe("@manual-smoke A — Password reset", () => {
  test("forgot-password → submit → Inbucket → click link → /reset-password → submit → /dashboard", async ({
    page,
  }) => {
    await page.goto(`${APP_URL}/forgot-password`);
    await page.getByLabel("Email").fill("dev@supabase.local");
    await page.getByRole("button", { name: /enviar enlace de recuperación/i }).click();

    // Success state appears (byte-identical for known / unknown email).
    await expect(page.getByRole("heading", { name: /revisá tu correo/i })).toBeVisible();

    // Fetch the recovery email from Inbucket.
    const { html } = await fetchLatestEmail((s) => /reset|password|recovery/i.test(s));
    const recoveryUrl = firstHref(html);

    // Click the recovery link.
    await page.goto(recoveryUrl);

    // Recovery session active → /reset-password renders the form.
    await expect(page).toHaveURL(/\/reset-password/);
    await page.getByLabel("Nueva contraseña").fill("new-test-password-1");
    await page.getByLabel("Confirmar contraseña").fill("new-test-password-1");
    await page.getByRole("button", { name: /actualizar contraseña/i }).click();

    // Successful update redirects to /dashboard.
    await page.waitForURL(/\/dashboard/, { timeout: 10_000 });
  });
});

// ---------------------------------------------------------------------------
// E — Magic-link login (SCN-AUTH-017)
// ---------------------------------------------------------------------------

test.describe("@manual-smoke E — Magic link login", () => {
  test("/login → click 'Enviar enlace mágico' → Inbucket → click → /dashboard", async ({
    page,
  }) => {
    await page.goto(`${APP_URL}/login`);
    // The OTP field is below the password form.
    await page.getByLabel(/tu correo electrónico/i).fill("dev@supabase.local");
    await page.getByRole("button", { name: /enviar enlace mágico/i }).click();

    // Success state appears.
    await expect(page.getByRole("heading", { name: /revisá tu correo/i })).toBeVisible();

    // Fetch the magic-link email.
    const { html } = await fetchLatestEmail((s) => /magic|sign|login/i.test(s));
    const magicUrl = firstHref(html);

    await page.goto(magicUrl);

    // Magic link → session created → /dashboard.
    await page.waitForURL(/\/dashboard/, { timeout: 10_000 });
  });
});

// ---------------------------------------------------------------------------
// C — Account deletion happy path (SCN-AUTH-011..012)
// ---------------------------------------------------------------------------

test.describe("@manual-smoke C — Account deletion", () => {
  test("sign in → /settings → 'Eliminar cuenta' → typed email → confirm → re-login fails", async ({
    page,
  }) => {
    const testEmail = "dev@supabase.local";
    const testPassword = "new-test-password-1"; // set in the previous A.1 test

    // 1. Sign in via the (now-known) password.
    await page.goto(`${APP_URL}/login`);
    await page.getByLabel("Email").fill(testEmail);
    await page.getByLabel("Contraseña").fill(testPassword);
    await page.getByRole("button", { name: /^entrar$/i }).click();
    await page.waitForURL(/\/dashboard/, { timeout: 10_000 });

    // 2. Navigate to settings and open the delete dialog.
    await page.goto(`${APP_URL}/settings`);
    await page.getByRole("button", { name: /eliminar cuenta/i }).first().click();

    // 3. Type the user's exact email (case-insensitive trim).
    await page
      .getByTestId("delete-account-confirm-input")
      .fill(`  ${testEmail.toUpperCase()}  `);
    await page.getByTestId("delete-account-confirm").click();

    // 4. After success, the dialog closes + the user is redirected to /.
    await page.waitForURL(`${APP_URL}/`, { timeout: 15_000 });

    // 5. Re-login with the same email/password fails with auth error.
    await page.goto(`${APP_URL}/login`);
    await page.getByLabel("Email").fill(testEmail);
    await page.getByLabel("Contraseña").fill(testPassword);
    await page.getByRole("button", { name: /^entrar$/i }).click();
    // The login page surfaces the auth error inline (no redirect).
    await expect(page.getByText(/invalid login credentials|credenciales/i)).toBeVisible({
      timeout: 5_000,
    });
  });
});
