import { describe, expect, it } from "vitest";

import { securityHeaders } from "./security-headers";

const value = (headers: { key: string; value: string }[], key: string) =>
  headers.find((h) => h.key === key)?.value;

describe("securityHeaders", () => {
  it("forbids framing, plugins and foreign form targets", () => {
    const csp = value(securityHeaders(false), "Content-Security-Policy") ?? "";
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain("object-src 'none'");
    expect(csp).toContain("form-action 'self'");
    expect(csp).toContain("base-uri 'self'");
    expect(value(securityHeaders(false), "X-Content-Type-Options")).toBe("nosniff");
  });

  it("sends HSTS only in production", () => {
    expect(value(securityHeaders(false), "Strict-Transport-Security")).toBeUndefined();
    expect(value(securityHeaders(true), "Strict-Transport-Security")).toContain("max-age=");
  });
});
