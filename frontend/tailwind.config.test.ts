/**
 * Tests for SCN-PDPRSC-005-C (REQ-PDPRSC-005) —
 * `frontend/tailwind.config.ts` MUST reference CSS variables
 * for the 3 font families (Inter, DM Sans, JetBrains Mono).
 *
 * The `next/font/google` self-hosting strategy in `app/layout.tsx`
 * exposes each font as a CSS variable (`--font-inter`,
 * `--font-dm-sans`, `--font-jetbrains-mono`). Tailwind's
 * `fontFamily.sans / display / mono` keys MUST consume those
 * variables so utility classes like `font-sans`, `font-display`,
 * and `font-mono` resolve to the self-hosted font.
 *
 * The test reads `tailwind.config.ts` as text and asserts each
 * of the 3 keys contains the corresponding `var(--font-*)`.
 * Pure string scan — no module evaluation (the file imports
 * `tailwindcss-animate` and resolves `Config` types).
 */

import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";

// `__dirname` already points at `frontend/` (this file lives at
// `frontend/tailwind.config.test.ts`), so the target file is a
// sibling — no `..` needed.
const TAILWIND_CONFIG_PATH = path.resolve(__dirname, "tailwind.config.ts");

describe("tailwind.config.ts — SCN-PDPRSC-005-C (font CSS variables)", () => {
  const source = fs.readFileSync(TAILWIND_CONFIG_PATH, "utf8");

  it("fontFamily.sans references var(--font-inter)", () => {
    // The fontFamily block opens with `fontFamily: {` then
    // 3 keys (sans, display, mono). Extract the sans block
    // by anchoring on `sans: [` ... `]` and assert it contains
    // the CSS variable reference.
    const sansMatch = source.match(/sans:\s*\[([^\]]+)\]/);
    expect(sansMatch).not.toBeNull();
    expect(sansMatch![1]).toContain("var(--font-inter)");
  });

  it("fontFamily.display references var(--font-dm-sans)", () => {
    const displayMatch = source.match(/display:\s*\[([^\]]+)\]/);
    expect(displayMatch).not.toBeNull();
    expect(displayMatch![1]).toContain("var(--font-dm-sans)");
  });

  it("fontFamily.mono references var(--font-jetbrains-mono)", () => {
    const monoMatch = source.match(/mono:\s*\[([^\]]+)\]/);
    expect(monoMatch).not.toBeNull();
    expect(monoMatch![1]).toContain("var(--font-jetbrains-mono)");
  });
});
