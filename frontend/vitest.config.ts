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
    ],
  },
});