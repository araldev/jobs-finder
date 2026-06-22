/**
 * Tests for SCN-PDPRSC-005-B (REQ-PDPRSC-005) —
 * `app/layout.tsx` MUST wire `next/font/google` for
 * Inter, DM Sans, and JetBrains Mono, and apply the
 * generated `--variable` classes to the `<body>` element.
 *
 * `next/font/google` returns a font object whose `.variable`
 * class embeds the CSS variable name (e.g.
 * `__variable_<hash>` for `--font-inter`). The variable
 * class is conventionally applied to `<body>` so child
 * elements inherit the CSS variable through cascade.
 *
 * The test asserts via FILE-CONTENT scan (instead of
 * `renderToStaticMarkup`) because the production layout is
 * an async server component using `await cookies()`; that
 * suspends under React 19, which `renderToStaticMarkup`
 * cannot complete. The file-content scan is the canonical
 * check for this SCN: the assertion is "the production
 * file wires next/font/google AND applies the variables to
 * `<body>`" — both pieces are byte-level facts about the
 * source. A render assertion would test the same thing
 * through a moving target (mocked `next/headers`, mocked
 * `next/font/google`); the file-content scan is more
 * robust against silent regressions.
 *
 * The 4 assertions cover:
 *   1. Each of the 3 fonts (Inter, DM_Sans, JetBrains_Mono)
 *      is imported from `next/font/google`.
 *   2. The font instances are constructed with
 *      `subsets: ["latin"]` and `display: "swap"` (the
 *      canonical anti-FOIT/anti-FOUT config).
 *   3. Each font instance declares its CSS variable name
 *      (`--font-inter`, `--font-dm-sans`, `--font-jetbrains-mono`).
 *   4. The `<body>` tag's className interpolates all 3
 *      `.variable` class names so the CSS variables reach
 *      every descendant.
 */

import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";

const LAYOUT_TSX_PATH = path.resolve(__dirname, "..", "layout.tsx");

describe("RootLayout — SCN-PDPRSC-005-B (next/font/google wiring)", () => {
  const source = fs.readFileSync(LAYOUT_TSX_PATH, "utf8");

  it("imports Inter, DM_Sans, and JetBrains_Mono from next/font/google", () => {
    expect(source).toMatch(
      /import\s*\{[^}]*\bInter\b[^}]*\}\s*from\s*["']next\/font\/google["']/,
    );
    expect(source).toMatch(
      /import\s*\{[^}]*\bDM_Sans\b[^}]*\}\s*from\s*["']next\/font\/google["']/,
    );
    expect(source).toMatch(
      /import\s*\{[^}]*\bJetBrains_Mono\b[^}]*\}\s*from\s*["']next\/font\/google["']/,
    );
  });

  it("instantiates each font with subsets=['latin'] and display='swap'", () => {
    // The ctor args are pinned to the canonical anti-FOIT config.
    // Anti-regression guard: a future refactor that drops `swap`
    // would re-introduce the FOIT (Flash of Invisible Text) that
    // the Lighthouse audit pinned as a CLS risk.
    expect(source).toMatch(/Inter\s*\(\s*\{[\s\S]*?subsets:\s*\[\s*"latin"\s*\][\s\S]*?\}\s*\)/);
    expect(source).toMatch(/DM_Sans\s*\(\s*\{[\s\S]*?subsets:\s*\[\s*"latin"\s*\][\s\S]*?\}\s*\)/);
    expect(source).toMatch(
      /JetBrains_Mono\s*\(\s*\{[\s\S]*?subsets:\s*\[\s*"latin"\s*\][\s\S]*?\}\s*\)/,
    );
    expect(source).toMatch(/Inter\s*\(\s*\{[\s\S]*?display:\s*"swap"[\s\S]*?\}\s*\)/);
    expect(source).toMatch(/DM_Sans\s*\(\s*\{[\s\S]*?display:\s*"swap"[\s\S]*?\}\s*\)/);
    expect(source).toMatch(
      /JetBrains_Mono\s*\(\s*\{[\s\S]*?display:\s*"swap"[\s\S]*?\}\s*\)/,
    );
  });

  it("declares each font's CSS variable name", () => {
    // The `variable:` arg on each font ctor pins the CSS
    // variable name that Tailwind's `fontFamily.sans/display/mono`
    // consumes (SCN-PDPRSC-005-C).
    expect(source).toMatch(/variable:\s*["']--font-inter["']/);
    expect(source).toMatch(/variable:\s*["']--font-dm-sans["']/);
    expect(source).toMatch(/variable:\s*["']--font-jetbrains-mono["']/);
  });

  it("applies all 3 .variable classes to the <body> tag", () => {
    // The `<body>` element MUST interpolate all 3 `.variable`
    // class strings so the CSS variables are reachable by every
    // descendant element. The exact regex looks for a `<body`
    // tag whose className template literal contains each
    // variable name. Class names are typically
    // `inter.variable` / `dmSans.variable` / `jetbrainsMono.variable`
    // — the test anchors on `.variable` to be agnostic to the
    // binding names a future refactor may choose.
    const bodyMatch = source.match(/<body[^>]*className=\{`[^`]*`\}/);
    expect(bodyMatch).not.toBeNull();
    const bodyClassName = bodyMatch![0];
    expect(bodyClassName).toMatch(/inter\.variable/);
    expect(bodyClassName).toMatch(/dmSans\.variable/);
    expect(bodyClassName).toMatch(/jetbrainsMono\.variable/);
  });
});
