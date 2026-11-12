import { describe, expect, it } from "vitest";

import { normalizeApiUrl } from "./env";

describe("normalizeApiUrl", () => {
  it("falls back to the local API when unset or blank", () => {
    expect(normalizeApiUrl(undefined)).toBe("http://localhost:8000/api/v1");
    expect(normalizeApiUrl("   ")).toBe("http://localhost:8000/api/v1");
  });

  it("strips trailing slashes", () => {
    expect(normalizeApiUrl("https://api.example.com/api/v1///")).toBe(
      "https://api.example.com/api/v1",
    );
  });

  it("rejects invalid URLs and non-http schemes", () => {
    expect(() => normalizeApiUrl("not a url")).toThrow(/valid URL/);
    expect(() => normalizeApiUrl("ftp://example.com")).toThrow(/http or https/);
  });
});
