import { describe, expect, it } from "vitest";

import { SAMPLE_SCENARIOS } from "@/mocks/scenarios";
import { REPORTS } from "@/mocks/workspace";

import {
  getDashboardSummary,
  periodTotals,
  regionPerformance,
  regionQuarterComparison,
  segmentPerformance,
  splitByWeights,
  sum,
  topProducts,
} from "./analytics";
import { findScenarioForQuestion } from "./index";

describe("splitByWeights", () => {
  it("parts always add up to the total", () => {
    for (const total of [0, 1, 999, 2_094_646]) {
      expect(sum(splitByWeights(total, [3, 1, 1, 7]))).toBe(total);
    }
  });
});

describe("demo data consistency", () => {
  it("regional Q3 revenue sums to the Q3 monthly total", () => {
    expect(sum(regionPerformance().map((r) => r.revenue))).toBe(periodTotals("q3").revenue);
  });

  it("region comparison Q2 column sums to the Q2 monthly total", () => {
    expect(sum(regionQuarterComparison().map((r) => r.q2))).toBe(periodTotals("q2").revenue);
  });

  it("segment revenue and orders sum to the 12-month totals", () => {
    const t = periodTotals("last12");
    const segments = segmentPerformance();
    expect(sum(segments.map((s) => s.revenue))).toBe(t.revenue);
    expect(sum(segments.map((s) => s.orders))).toBe(t.orders);
  });

  it("top products are sorted and never exceed year-to-date revenue", () => {
    const products = topProducts();
    const revenues = products.map((p) => p.revenue);
    expect(revenues).toEqual([...revenues].sort((a, b) => b - a));
    expect(sum(revenues)).toBeLessThan(periodTotals("ytd").revenue);
  });

  it("dashboard KPIs are derived from the series", () => {
    const summary = getDashboardSummary();
    const revenue = summary.kpis.find((k) => k.key === "revenue");
    expect(revenue?.value).toBe(periodTotals("last12").revenue);
    expect(summary.revenueTrend).toHaveLength(12);
    const growth = summary.kpis.find((k) => k.key === "growth");
    expect(growth?.value).toBeCloseTo(
      periodTotals("last12").revenue / periodTotals("previous12").revenue - 1,
      10,
    );
  });
});

describe("sample scenarios follow the grounding rule", () => {
  it("every insight in an answered scenario cites evidence", () => {
    for (const s of SAMPLE_SCENARIOS) {
      for (const insight of s.result.insights) {
        expect(insight.evidence.length, `${s.id}/${insight.id}`).toBeGreaterThan(0);
      }
    }
  });

  it("row evidence points at rows that exist", () => {
    for (const s of SAMPLE_SCENARIOS) {
      const rows = s.result.table?.rows.length ?? 0;
      for (const insight of s.result.insights) {
        for (const ev of insight.evidence) {
          for (const index of ev.rowIndices ?? []) {
            expect(index, `${s.id}/${insight.id}`).toBeGreaterThanOrEqual(0);
            expect(index, `${s.id}/${insight.id}`).toBeLessThan(rows);
          }
        }
      }
    }
  });

  it("each scenario has exactly one accepted SQL attempt unless it stopped before SQL", () => {
    for (const s of SAMPLE_SCENARIOS) {
      const accepted = s.result.sqlAttempts.filter((a) => a.status === "accepted").length;
      expect(accepted, s.id).toBe(s.result.table ? 1 : 0);
    }
  });

  it("chart axes reference real result columns", () => {
    for (const s of SAMPLE_SCENARIOS) {
      if (!s.result.chart || !s.result.table) continue;
      const names = s.result.table.columns.map((c) => c.name);
      expect(names).toContain(s.result.chart.x);
      for (const y of s.result.chart.y) expect(names).toContain(y);
    }
  });

  it("reports are built from scenarios", () => {
    expect(REPORTS.length).toBeGreaterThan(0);
    for (const r of REPORTS) expect(r.insights.length).toBeGreaterThan(0);
  });
});

describe("findScenarioForQuestion", () => {
  it("matches the same question regardless of case and punctuation", () => {
    expect(
      findScenarioForQuestion(
        "which regions grew revenue fastest from q2 to q3 2026",
        "ds_retail_demo",
      )?.id,
    ).toBe("sc_regions");
  });

  it("never matches a different question", () => {
    expect(
      findScenarioForQuestion("Which regions grew orders fastest?", "ds_retail_demo"),
    ).toBeUndefined();
    expect(
      findScenarioForQuestion(
        "What are our top 10 products by revenue this year?",
        "ds_marketing_2026",
      ),
    ).toBeUndefined();
  });
});
