import { describe, it, expect } from "vitest";
import { formatRelativeDate, formatNumber, getPlatformColorClass } from "../formatters";

describe("formatRelativeDate", () => {
  it("returns empty string for null", () => {
    expect(formatRelativeDate(null)).toBe("");
  });

  it("returns relative time for recent dates", () => {
    const recent = new Date(Date.now() - 3600000).toISOString();
    expect(formatRelativeDate(recent)).toContain("hour");
  });
});

describe("formatNumber", () => {
  it("formats numbers with locale separators", () => {
    expect(formatNumber(1000)).toBe("1,000");
  });

  it("handles zero", () => {
    expect(formatNumber(0)).toBe("0");
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
