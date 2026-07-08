import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

/**
 * next-intl plugin — auto-invokes `getRequestConfig` from
 * `src/i18n/request.ts` during the build so RSC + static rendering pick
 * up the right locale and message bundle. Required by next-intl 3.x+;
 * without this wrapper, `getMessages()` inside `app/layout.tsx` would
 * fail at build time with "no messages found for locale 'es'".
 *
 * The path is relative to the project root (where `next.config.ts`
 * lives). Closes REQ-I18N-001.
 */
const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

const nextConfig: NextConfig = {
  // No experimental features needed for v1

  // Phase 3 PDF dependencies are CJS-only with internal module-wrapping
  // that Webpack chokes on when treated as ESM ("Cannot read properties
  // of undefined (reading 'call')" at module init). Listing them here
  // tells Next.js to load them via `require()` from the server bundle
  // instead of running them through the ESM transform pipeline.
  // The runtime code is unchanged — they still work the same once
  // loaded via the CJS path.
  //
  // @napi-rs/canvas is a NATIVE Node addon (skia.linux-x64-gnu.node
  // etc.) — it can never be bundled by webpack (it's a binary,
  // not JS). Marking it as serverExternalPackages prevents
  // webpack from trying to walk the import graph from the
  // CLIENT bundle. We also use a dynamic `await import(...)` in
  // the source so even if webpack DOES see the import, it
  // can't statically resolve it and skips the chunk.
  serverExternalPackages: ["pdf-lib", "unpdf", "@napi-rs/canvas"],
};

export default withNextIntl(nextConfig);