import { describe, expect, it } from "vitest";

import { fileSlug } from "./download";

describe("fileSlug", () => {
  it("makes a header-safe ASCII filename from a title", () => {
    expect(fileSlug("Q3 revenue — by region!", "pdf")).toBe("q3-revenue-by-region.pdf");
  });
  it("falls back when nothing ASCII is left", () => {
    expect(fileSlug("日本語", "pdf")).toBe("report.pdf");
    expect(fileSlug("   ", "md")).toBe("report.md");
  });
  it("is capped so very long questions don’t make unwieldy names", () => {
    expect(fileSlug("a".repeat(300), "pdf").length).toBe(64);
  });
});
