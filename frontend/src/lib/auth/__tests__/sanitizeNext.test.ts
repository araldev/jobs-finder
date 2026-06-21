import { describe, it, expect } from "vitest";
import { sanitizeNext } from "../sanitizeNext";

describe("sanitizeNext", () => {
  // Allowed cases
  it.each([
    ["/dashboard", "/dashboard"],
    ["/reset-password", "/reset-password"],
    ["/jobs/123", "/jobs/123"],
    ["/forgot-password", "/forgot-password"],
    ["/search?q=react", "/search?q=react"],
    ["/settings/account", "/settings/account"],
  ])("returns '%s' unchanged", (input, expected) => {
    expect(sanitizeNext(input)).toBe(expected);
  });

  // Rejected cases — all fall back to /dashboard
  describe("rejects unsafe values", () => {
    it("missing (null) → /dashboard", () => {
      expect(sanitizeNext(null)).toBe("/dashboard");
    });

    it("empty string → /dashboard", () => {
      expect(sanitizeNext("")).toBe("/dashboard");
    });

    it("protocol-relative URL '//evil.com' → /dashboard", () => {
      expect(sanitizeNext("//evil.com")).toBe("/dashboard");
    });

    it("protocol-relative URL '//evil.com/path' → /dashboard", () => {
      expect(sanitizeNext("//evil.com/path")).toBe("/dashboard");
    });

    it("absolute https URL 'https://evil.com' → /dashboard", () => {
      expect(sanitizeNext("https://evil.com")).toBe("/dashboard");
    });

    it("absolute http URL 'http://evil.com' → /dashboard", () => {
      expect(sanitizeNext("http://evil.com")).toBe("/dashboard");
    });

    it("backslash-trick '/\\\\evil.com' → /dashboard", () => {
      // The `//` check catches this — `\\` is not `/`, but the leading
      // `/` followed by a backslash still doesn't match a clean path.
      // The validator should be conservative and reject.
      expect(sanitizeNext("/\\evil.com")).toBe("/dashboard");
    });

    it("javascript: URI 'javascript:alert(1)' → /dashboard", () => {
      expect(sanitizeNext("javascript:alert(1)")).toBe("/dashboard");
    });

    it("data URI 'data:text/html,...' → /dashboard", () => {
      expect(sanitizeNext("data:text/html,<script>")).toBe("/dashboard");
    });

    it("lone '/' (no path) → /dashboard", () => {
      expect(sanitizeNext("/")).toBe("/dashboard");
    });
  });
});
