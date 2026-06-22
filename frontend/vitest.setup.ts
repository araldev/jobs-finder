import "@testing-library/jest-dom/vitest";

// jsdom doesn't implement matchMedia by default — next-themes calls it
// at module-load time, so we have to stub it before any test imports a
// component that pulls in next-themes (via ThemeProvider in test-utils).
if (typeof window !== "undefined" && !window.matchMedia) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {}, // deprecated but next-themes may call it
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });
}