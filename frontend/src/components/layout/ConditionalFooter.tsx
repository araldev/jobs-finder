"use client";

import { useSelectedLayoutSegment } from "next/navigation";
import { Footer } from "./Footer";

/**
 * Locale-scoped footer wrapper that hides the marketing Footer on the
 * `(app)` route group (dashboard, search, favorites, settings) where the
 * in-app `AppShell` already consumes the full viewport. On every other
 * route — public marketing pages, auth pages, job detail, root landing —
 * it renders the normal `Footer` so users see the privacy link and
 * copyright notice.
 *
 * The guard uses `useSelectedLayoutSegment("(app)")` from Next.js 15: it
 * returns the active segment inside the `(app)` parallel slot, or `null`
 * when no segment in that slot is active. Rendering nothing when the
 * segment is non-null prevents the dangling-Footer bug observed when
 * `AppShell` (h-screen) sits inside a min-h-screen flex column that
 * also renders a sibling Footer.
 *
 * NOTE: This file was added in `fix-frontend-root-layout-tags` to fix
 * the runtime "Missing <html> and <body>" error. It is duplicated from
 * `feat-frontend-i18n-complete-coverage` (commit ec904cd) which has
 * not been merged to `main` yet. When that PR merges, git will detect
 * the identical-content conflict and either side can be accepted —
 * the implementation is intentionally byte-identical.
 */
export function ConditionalFooter() {
  const appSegment = useSelectedLayoutSegment("(app)");
  if (appSegment !== null) return null;
  return <Footer />;
}
