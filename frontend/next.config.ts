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
};

export default withNextIntl(nextConfig);