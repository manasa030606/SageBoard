import { describe, expect, it } from "vitest";

import { binValues } from "./histogram";

describe("binValues", () => {
  it("bins numbers into friendly equal-width intervals covering every value", () => {
    const values = Array.from({ length: 100 }, (_, i) => i + 1); // 1..100
    const bins = binValues(values);
    expect(bins.length).toBeGreaterThanOrEqual(8);
    expect(bins.length).toBeLessThanOrEqual(13);
    expect(bins.reduce((acc, b) => acc + b.count, 0)).toBe(100);
    expect(bins[0]?.bin).toMatch(/^0–/);
  });

  it("handles numeric strings, ignores junk, and survives identical values", () => {
    expect(binValues(["5", "5", null, "x", 5])).toEqual([{ bin: "5", count: 3 }]);
    expect(binValues([])).toEqual([]);
  });

  it("labels large values compactly", () => {
    const bins = binValues([10_000, 250_000, 990_000]);
    expect(bins.reduce((acc, b) => acc + b.count, 0)).toBe(3);
    expect(bins[0]?.bin).toMatch(/K/);
  });
});
