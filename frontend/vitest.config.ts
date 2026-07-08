import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: "./vitest.setup.ts",
    globals: true,
    // The e2e/ folder holds Playwright specs (run via `playwright test`,
    // NOT vitest). Excluding them here keeps `npm run test` green.
    exclude: [
      "**/node_modules/**",
      "**/dist/**",
      "**/.next/**",
      "e2e/**",
    ],
  },
  resolve: {
    alias: [
      // More specific first — @/messages must NOT match the generic @ alias.
      // Mirror the tsconfig `@/messages/*` path alias for JSON imports.
      { find: /^@\/messages\/(.*)$/, replacement: path.resolve(__dirname, "./messages/$1") },
      { find: "@", replacement: path.resolve(__dirname, "./src") },
      // `server-only` is a Next.js convention — in the Next.js webpack
      // build it's a no-op for server modules and a hard error for
      // client modules. In vitest we treat it as a no-op so we can
      // unit-test server-only modules directly. (Server-only modules
      // that have client-side data dependencies are still excluded
      // from the client bundle by Next.js at build time.)
      { find: /^server-only$/, replacement: path.resolve(__dirname, "vitest.server-only-shim.ts") },
    ],
  },
});