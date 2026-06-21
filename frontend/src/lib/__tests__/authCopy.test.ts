import { describe, it, expect } from "vitest";
import { authCopy } from "../authCopy";

/**
 * authCopy is the SINGLE source of truth for every user-facing Spanish
 * string introduced by the auth-flows change (REQ-AUTH-023). No inline
 * Spanish literals SHALL appear in components/pages.
 *
 * This test enforces the contract by recursively walking every leaf of
 * the frozen `authCopy` object and asserting that no string is empty
 * or whitespace-only. A failure here means a new copy string was added
 * with an empty value — fix the copy, not the test.
 */
describe("authCopy", () => {
  function walk(value: unknown, path: string): void {
    if (typeof value === "string") {
      it(`has non-empty copy at ${path}`, () => {
        expect(value.trim().length).toBeGreaterThan(0);
      });
      return;
    }
    if (value && typeof value === "object") {
      for (const [k, v] of Object.entries(value)) {
        walk(v, `${path}.${k}`);
      }
    }
  }

  walk(authCopy, "authCopy");

  it("is frozen at the top level", () => {
    expect(Object.isFrozen(authCopy)).toBe(true);
  });

  it("includes the required top-level groups", () => {
    expect(authCopy).toHaveProperty("forgot");
    expect(authCopy).toHaveProperty("reset");
    expect(authCopy).toHaveProperty("change");
    expect(authCopy).toHaveProperty("delete");
    expect(authCopy).toHaveProperty("banner");
    expect(authCopy).toHaveProperty("magicLink");
    expect(authCopy).toHaveProperty("validation");
    expect(authCopy).toHaveProperty("toast");
  });

  it("password length error mentions '6' (the rule)", () => {
    expect(authCopy.validation.passwordMinLength).toContain("6");
  });

  it("passwords-mismatch error is in Spanish", () => {
    expect(authCopy.validation.passwordsDoNotMatch).toBe(
      "Las contraseñas no coinciden",
    );
  });

  it("delete confirmation copy explains irreversibility in Spanish", () => {
    expect(authCopy.delete.destructiveHelp).toMatch(/[Aa]cción|[Ii]rreversible|[Ee]liminar/);
  });
});
