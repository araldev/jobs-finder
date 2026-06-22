import { describe, it, expect } from "vitest";
import esMessages from "@/messages/es.json";
import enMessages from "@/messages/en.json";

/**
 * Regression: EN/ES message parity for the latency hint added in
 * REQ-CACHEUX-007. Without both locales defining `Dashboard.loadingHint`
 * and `Common.loadingHint`, the skeleton shows the raw i18n key
 * ("Dashboard.loadingHint") instead of the user-friendly text. The
 * tests assert the keys exist AND are non-empty strings AND that
 * EN/ES have parity (both files define the same keys).
 */
describe("messages parity — Dashboard.loadingHint + Common.loadingHint", () => {
  it("en.json defines Dashboard.loadingHint as a non-empty string", () => {
    const value = enMessages.Dashboard?.loadingHint;
    expect(typeof value).toBe("string");
    expect((value as string).length).toBeGreaterThan(0);
  });

  it("es.json defines Dashboard.loadingHint as a non-empty string", () => {
    const value = esMessages.Dashboard?.loadingHint;
    expect(typeof value).toBe("string");
    expect((value as string).length).toBeGreaterThan(0);
  });

  it("en.json defines Common.loadingHint as a non-empty string", () => {
    const value = enMessages.Common?.loadingHint;
    expect(typeof value).toBe("string");
    expect((value as string).length).toBeGreaterThan(0);
  });

  it("es.json defines Common.loadingHint as a non-empty string", () => {
    const value = esMessages.Common?.loadingHint;
    expect(typeof value).toBe("string");
    expect((value as string).length).toBeGreaterThan(0);
  });

  it("EN and ES loadingHint values are both present (parity)", () => {
    // The keys must be defined in BOTH locales so neither falls back
    // to a raw key render. The actual strings may differ in language
    // (EN vs ES), but neither side can be missing.
    expect(enMessages.Dashboard?.loadingHint).toBeTruthy();
    expect(esMessages.Dashboard?.loadingHint).toBeTruthy();
    expect(enMessages.Common?.loadingHint).toBeTruthy();
    expect(esMessages.Common?.loadingHint).toBeTruthy();
  });
});
