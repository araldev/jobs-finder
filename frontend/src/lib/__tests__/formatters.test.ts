import { describe, it, expect } from "vitest";
import {
  formatRelativeDate,
  formatNumber,
  getPlatformColorClass,
} from "../formatters";

describe("formatRelativeDate — bilingual", () => {
  it("returns empty string for null", () => {
    expect(formatRelativeDate(null)).toBe("");
    expect(formatRelativeDate(null, "en")).toBe("");
  });

  it("Spanish: recent (same-day) dates use 'hace' suffix", () => {
    // 1 hour ago — definitely today, not yesterday
    const oneHourAgo = new Date(Date.now() - 1 * 3600000).toISOString();
    expect(formatRelativeDate(oneHourAgo, "es")).toContain("hace");
  });

  it("English: recent (same-day) dates use 'ago' suffix", () => {
    const oneHourAgo = new Date(Date.now() - 1 * 3600000).toISOString();
    expect(formatRelativeDate(oneHourAgo, "en")).toMatch(/ago|hours?/);
  });

  it("Spanish: yesterday returns 'Ayer'", () => {
    const yesterday = new Date(Date.now() - 24 * 3600000).toISOString();
    expect(formatRelativeDate(yesterday, "es")).toBe("Ayer");
  });

  it("English: yesterday returns 'Yesterday'", () => {
    const yesterday = new Date(Date.now() - 24 * 3600000).toISOString();
    expect(formatRelativeDate(yesterday, "en")).toBe("Yesterday");
  });

  it("Default locale is Spanish (no arg → 'es')", () => {
    const oneHourAgo = new Date(Date.now() - 1 * 3600000).toISOString();
    expect(formatRelativeDate(oneHourAgo)).toContain("hace");
  });
});

describe("formatNumber — bilingual", () => {
  it("Spanish: 12345.5 uses '.' as thousands separator and ',' as decimal", () => {
    // Intl.NumberFormat('es') uses period for thousands and comma for decimals.
    // (4-digit numbers don't trigger grouping in some environments, so
    // we use 5-digit numbers to exercise the separator behavior.)
    expect(formatNumber(12345.5, "es")).toBe("12.345,5");
  });

  it("English: 12345.5 uses ',' as thousands separator and '.' as decimal", () => {
    expect(formatNumber(12345.5, "en")).toBe("12,345.5");
  });

  it("Default locale is Spanish (no arg → 'es')", () => {
    expect(formatNumber(10000)).toBe("10.000");
  });

  it("handles zero", () => {
    expect(formatNumber(0, "es")).toBe("0");
    expect(formatNumber(0, "en")).toBe("0");
  });

  it("handles negative numbers", () => {
    expect(formatNumber(-42500.5, "es")).toBe("-42.500,5");
    expect(formatNumber(-42500.5, "en")).toBe("-42,500.5");
  });
});

describe("getPlatformColorClass", () => {
  it("returns linkedin color class", () => {
    expect(getPlatformColorClass("linkedin")).toContain("--linkedin");
  });

  it("returns indeed color class", () => {
    expect(getPlatformColorClass("indeed")).toContain("--indeed");
  });

  it("returns infojobs color class", () => {
    expect(getPlatformColorClass("infojobs")).toContain("--infojobs");
  });

  it("returns muted for unknown platform", () => {
    expect(getPlatformColorClass("unknown")).toBe("bg-muted");
  });

  it("is case insensitive", () => {
    expect(getPlatformColorClass("LinkedIn")).toContain("--linkedin");
  });
});