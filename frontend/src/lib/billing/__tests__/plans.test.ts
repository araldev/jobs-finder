// Tests for the plan constants table.
//
// Pure-data module — no mocks, no I/O. The constants table is the
// single source of truth for plan limits, so any drift between the
// spec and the runtime tables here will surface as a real assertion
// failure (not a smoke test).

import { describe, it, expect } from "vitest";

import { PLANS, getPlanConfig } from "../plans";
import type { PlanName } from "@/types/billing";

describe("PLANS — plan constants table (source of truth for limits)", () => {
  it("defines exactly three plans: free, pro, pro_plus", () => {
    expect(Object.keys(PLANS).sort()).toEqual(
      ["free", "pro", "pro_plus"].sort(),
    );
  });

  it("Free: 3 CV/month, 3 saved searches, no notifications, ENABLED (the default)", () => {
    const free = PLANS.free;
    expect(free.name).toBe("free");
    expect(free.displayName).toBe("Free");
    expect(free.cvLimitPerMonth).toBe(3);
    expect(free.savedSearchLimit).toBe(3);
    expect(free.notificationsEnabled).toBe(false);
    expect(free.enabled).toBe(true);
  });

  it("Pro: UNLIMITED CVs, 20 saved searches, notifications ENABLED, enabled=true", () => {
    const pro = PLANS.pro;
    expect(pro.name).toBe("pro");
    expect(pro.displayName).toBe("Pro");
    expect(pro.cvLimitPerMonth).toBe("unlimited");
    expect(pro.savedSearchLimit).toBe(20);
    expect(pro.notificationsEnabled).toBe(true);
    expect(pro.enabled).toBe(true);
  });

  it("Pro Plus: UNLIMITED everything, notifications enabled, but enabled=false (locked)", () => {
    const proPlus = PLANS.pro_plus;
    expect(proPlus.name).toBe("pro_plus");
    expect(proPlus.displayName).toBe("Pro Plus");
    expect(proPlus.cvLimitPerMonth).toBe("unlimited");
    expect(proPlus.savedSearchLimit).toBe("unlimited");
    expect(proPlus.notificationsEnabled).toBe(true);
    // Pro Plus is a future-proof schema slot; UI must show it disabled.
    expect(proPlus.enabled).toBe(false);
  });

  it("getPlanConfig(plan) returns the matching config (no default fallback)", () => {
    expect(getPlanConfig("free").cvLimitPerMonth).toBe(3);
    expect(getPlanConfig("pro").cvLimitPerMonth).toBe("unlimited");
    expect(getPlanConfig("pro_plus").enabled).toBe(false);
  });

  it("PLANS values are type-narrowed to PlanName (compile-time + runtime check)", () => {
    // Each key must be a valid PlanName. If the union ever gains a
    // member, this test catches drift.
    const expectedKeys: PlanName[] = ["free", "pro", "pro_plus"];
    for (const key of expectedKeys) {
      expect(PLANS[key].name).toBe(key);
    }
  });
});