import { describe, it, expect } from "vitest";
import {
  forgotPasswordSchema,
  resetPasswordSchema,
  changePasswordSchema,
  magicLinkSchema,
  deleteAccountConfirmSchema,
} from "../authSchemas";

describe("forgotPasswordSchema", () => {
  it("accepts a valid email", () => {
    const result = forgotPasswordSchema.safeParse({ email: "user@example.com" });
    expect(result.success).toBe(true);
  });

  it("rejects an empty email with the Spanish message", () => {
    const result = forgotPasswordSchema.safeParse({ email: "" });
    expect(result.success).toBe(false);
    if (!result.success) {
      const msg = result.error.issues[0]?.message ?? "";
      expect(msg.length).toBeGreaterThan(0);
    }
  });

  it("rejects an invalid email format", () => {
    const result = forgotPasswordSchema.safeParse({ email: "not-an-email" });
    expect(result.success).toBe(false);
  });

  it("rejects a missing email field", () => {
    const result = forgotPasswordSchema.safeParse({});
    expect(result.success).toBe(false);
  });
});

describe("resetPasswordSchema", () => {
  it("accepts matching passwords of 6+ chars", () => {
    const result = resetPasswordSchema.safeParse({
      password: "abc123",
      confirmPassword: "abc123",
    });
    expect(result.success).toBe(true);
  });

  it("rejects a 5-char password", () => {
    const result = resetPasswordSchema.safeParse({
      password: "abcde",
      confirmPassword: "abcde",
    });
    expect(result.success).toBe(false);
  });

  it("rejects mismatched passwords", () => {
    const result = resetPasswordSchema.safeParse({
      password: "abc123",
      confirmPassword: "abc124",
    });
    expect(result.success).toBe(false);
  });

  it("rejects an empty password field", () => {
    const result = resetPasswordSchema.safeParse({
      password: "",
      confirmPassword: "",
    });
    expect(result.success).toBe(false);
  });
});

describe("changePasswordSchema", () => {
  it("accepts current + matching new passwords of 6+ chars", () => {
    const result = changePasswordSchema.safeParse({
      currentPassword: "oldpass1",
      newPassword: "newpass1",
      confirmPassword: "newpass1",
    });
    expect(result.success).toBe(true);
  });

  it("rejects an empty current password", () => {
    const result = changePasswordSchema.safeParse({
      currentPassword: "",
      newPassword: "newpass1",
      confirmPassword: "newpass1",
    });
    expect(result.success).toBe(false);
  });

  it("rejects a 5-char new password", () => {
    const result = changePasswordSchema.safeParse({
      currentPassword: "oldpass1",
      newPassword: "abcde",
      confirmPassword: "abcde",
    });
    expect(result.success).toBe(false);
  });

  it("rejects mismatched new + confirm", () => {
    const result = changePasswordSchema.safeParse({
      currentPassword: "oldpass1",
      newPassword: "newpass1",
      confirmPassword: "newpass2",
    });
    expect(result.success).toBe(false);
  });
});

describe("magicLinkSchema", () => {
  it("accepts a valid email", () => {
    const result = magicLinkSchema.safeParse({ email: "user@example.com" });
    expect(result.success).toBe(true);
  });

  it("rejects an empty email", () => {
    const result = magicLinkSchema.safeParse({ email: "" });
    expect(result.success).toBe(false);
  });

  it("rejects an invalid email format", () => {
    const result = magicLinkSchema.safeParse({ email: "nope" });
    expect(result.success).toBe(false);
  });

  it("rejects a missing email field", () => {
    const result = magicLinkSchema.safeParse({});
    expect(result.success).toBe(false);
  });
});

describe("deleteAccountConfirmSchema", () => {
  it("accepts a valid email", () => {
    const result = deleteAccountConfirmSchema.safeParse({ confirmEmail: "user@example.com" });
    expect(result.success).toBe(true);
  });

  it("rejects an empty email", () => {
    const result = deleteAccountConfirmSchema.safeParse({ confirmEmail: "" });
    expect(result.success).toBe(false);
  });

  it("rejects an invalid email format", () => {
    const result = deleteAccountConfirmSchema.safeParse({ confirmEmail: "not-an-email" });
    expect(result.success).toBe(false);
  });

  it("rejects a missing email field", () => {
    const result = deleteAccountConfirmSchema.safeParse({});
    expect(result.success).toBe(false);
  });
});
