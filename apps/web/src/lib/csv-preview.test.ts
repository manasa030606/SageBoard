import { describe, expect, it } from "vitest";

import { inferType, parseCsvLine, previewCsv, validateUpload } from "./csv-preview";

describe("validateUpload", () => {
  it("accepts csv/xlsx within the limit", () => {
    expect(validateUpload({ name: "Sales.CSV", size: 1200 })).toBeNull();
    expect(validateUpload({ name: "book.xlsx", size: 1200 })).toBeNull();
  });
  it("rejects other types, empty and oversized files", () => {
    expect(validateUpload({ name: "data.json", size: 10 })).toMatch(/Only/);
    expect(validateUpload({ name: "a.csv", size: 0 })).toMatch(/empty/);
    expect(validateUpload({ name: "a.csv", size: 30 * 1024 * 1024 })).toMatch(/limit is 25 MB/);
  });
});

describe("parseCsvLine", () => {
  it("handles quotes, escaped quotes and delimiters inside quotes", () => {
    expect(parseCsvLine('a,"b, c","say ""hi"""', ",")).toEqual(["a", "b, c", 'say "hi"']);
  });
});

describe("inferType", () => {
  it.each([
    [["1", "2", "3"], "integer"],
    [["1.5", "2", "$1,200.50"], "numeric"],
    [["2026-01-01", "2026-02-01"], "date"],
    [["2026-01-01 10:00", "2026-01-02T11:30:00"], "timestamptz"],
    [["yes", "No"], "boolean"],
    [["1", "N/A", "3"], "integer"],
    [["1", "two"], "text"],
    [["", "NA"], "text"],
  ])("%j → %s", (values, expected) => {
    expect(inferType(values)).toBe(expected);
  });
});

describe("previewCsv", () => {
  it("detects semicolons and infers per-column types", () => {
    const p = previewCsv("order_id;order_date;amount\n1;2026-01-02;19.90\n2;2026-01-03;5\n");
    expect(p.delimiter).toBe(";");
    expect(p.columns.map((c) => c.suggestedType)).toEqual(["integer", "date", "numeric"]);
    expect(p.sampleRowCount).toBe(2);
  });

  it("throws a readable error for an empty file", () => {
    expect(() => previewCsv("\n\n")).toThrow(/no header/);
  });
});
