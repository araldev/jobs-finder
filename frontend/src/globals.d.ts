/**
 * Ambient module declarations for non-TS asset imports.
 *
 * Without these, `import "./globals.css"` and similar side-effect imports
 * raise TS2882 ("Cannot find module or type declarations for side-effect
 * import") in the IDE / `tsc --noEmit`, even though Next.js + Webpack/Turbopack
 * handle the file at build time.
 *
 * `declare module "*.css"` covers every CSS file in the project (root +
 * nested). The wildcard pattern is the canonical convention; do NOT
 * narrow it to specific filenames.
 *
 * Adding `declare module "*.scss"` etc. is unnecessary right now — the
 * project ships only Tailwind CSS compiled to a single `globals.css`
 * (no Sass/Less source files). Add patterns here as the project grows.
 *
 * This file is auto-loaded by tsc because it lives under `src/` and the
 * tsconfig `include` covers it. No registration needed.
 */

declare module "*.css";
declare module "pngjs";
