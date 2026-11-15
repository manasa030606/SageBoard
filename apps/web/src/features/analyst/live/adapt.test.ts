import { describe, expect, it } from "vitest";

import type { NodeRun, WireChart, WireFact, WireInsight, WireStep } from "@/lib/api/types";

import { adaptChart, adaptInsight, adaptStep, adaptTimeline, liveActivity } from "./adapt";

const STEP: WireStep = {
  step_id: "s1",
  purpose: "Revenue by category",
  expected_output: "one row per category",
  depends_on: [],
  status: "succeeded",
  sql: "SELECT category, revenue FROM t LIMIT 501",
  explanation: "e",
  attempts: [
    {
      attempt: 1,
      sql: "SELECT bad",
      explanation: "",
      origin: "generation",
      guard_status: "rejected",
      guard_violations: [{ code: "UNKNOWN_COLUMN", message: "no such column" }],
      normalized_sql: null,
      exec_status: "not_run",
      error_code: null,
      exec_error: null,
      exec_ms: null,
      row_count: null,
      diagnosis: { category: "unknown_column", recoverable: true, summary: "s", hint: null },
    },
    {
      attempt: 2,
      sql: "SELECT category, revenue FROM t",
      explanation: "",
      origin: "recovery",
      guard_status: "accepted",
      guard_violations: [],
      normalized_sql: "SELECT category, revenue FROM t LIMIT 501",
      exec_status: "ok",
      error_code: null,
      exec_error: null,
      exec_ms: 42,
      row_count: 2,
      diagnosis: null,
    },
  ],
  columns: [
    { name: "category", type: "text" },
    { name: "revenue", type: "numeric" },
    { name: "order_count", type: "int8" },
    { name: "first_order", type: "timestamptz" },
  ],
  row_count: 2,
  truncated: false,
  rows: [
    ["Electronics", 1200.5, 7, "2026-09-01T00:00:00+00:00"],
    ["Home", null, 3, "2026-09-02T10:30:00+00:00"],
  ],
  notes: [],
  failure_explanation: null,
};

describe("toResultTable / adaptStep", () => {
  it("maps names, formats and cells (nulls, midnight timestamps)", () => {
    const table = adaptStep(STEP).table;
    expect(table?.columns).toEqual([
      { name: "category", label: "Category", format: "text" },
      { name: "revenue", label: "Revenue", format: "number" },
      { name: "order_count", label: "Order count", format: "integer" },
      { name: "first_order", label: "First order", format: "text" },
    ]);
    expect(table?.rows[0]).toEqual({
      category: "Electronics",
      revenue: 1200.5,
      order_count: 7,
      first_order: "2026-09-01", // midnight timestamp trimmed to the date
    });
    expect(table?.rows[1]?.revenue).toBe("");
    expect(table?.rows[1]?.first_order).toBe("2026-09-02T10:30:00+00:00");
  });

  it("maps attempts: rejected → corrected → accepted, keeping violations", () => {
    const step = adaptStep(STEP);
    expect(step.attempts.map((a) => a.status)).toEqual(["rejected", "accepted"]);
    expect(step.attempts[0]?.violations[0]?.code).toBe("UNKNOWN_COLUMN");
    expect(step.attempts[1]?.sql).toContain("LIMIT 501");
  });
});

describe("adaptChart", () => {
  const chart: WireChart = {
    chart_type: "grouped_bar",
    step_id: "s1",
    x: "category",
    y: ["revenue"],
    series: null,
    title: "Revenue by category",
    subtitle: null,
    value_format: "currency",
    fallback_reason: null,
    data: [["Electronics", 1200.5]],
    columns: ["category", "revenue"],
  };

  it("builds the chart table with types from the source step", () => {
    const adapted = adaptChart(chart, [STEP]);
    expect(adapted.spec.chartType).toBe("grouped_bar");
    expect(adapted.table?.columns[1]).toMatchObject({ name: "revenue", format: "number" });
    expect(adapted.table?.rows[0]?.category).toBe("Electronics");
  });

  it("returns no table when the chart carries no data", () => {
    expect(adaptChart({ ...chart, data: [] }, [STEP]).table).toBeNull();
  });
});

describe("adaptInsight", () => {
  const facts = new Map<string, WireFact>([
    [
      "f3",
      {
        fact_id: "f3",
        step_id: "s1",
        kind: "pct_change",
        description: "Change in total revenue",
        value: -15,
        unit: "%",
        inputs: {},
      },
    ],
  ]);
  const steps = new Map([["s1", STEP]]);
  const insight: WireInsight = {
    insight_id: "i1",
    headline: "Revenue fell 15%",
    detail: "d",
    category: "finding",
    evidence: [
      { kind: "fact", fact_id: "f3", step_id: null, row_index: null, column: null },
      { kind: "cell", fact_id: null, step_id: "s1", row_index: 0, column: "revenue" },
    ],
    confidence: "high",
    verification: "verified",
    rejection_reasons: [],
  };

  it("resolves fact and cell evidence to labels, values and step links", () => {
    const adapted = adaptInsight(insight, facts, steps);
    expect(adapted.evidence[0]).toEqual({
      kind: "fact",
      label: "Change in total revenue",
      value: "-15%",
    });
    expect(adapted.evidence[1]).toMatchObject({
      kind: "rows",
      label: "Revenue",
      rowIndices: [0],
      value: "1,200.5",
      stepId: "s1",
    });
  });
});

describe("adaptTimeline / liveActivity", () => {
  const trace: NodeRun[] = [
    {
      seq: 1,
      node: "understand_query",
      status: "succeeded",
      started_at: "2026-11-15T10:00:00Z",
      duration_ms: 1200,
      summary: { status: "answerable", intent: "comparison", metrics: ["revenue"] },
      tool_calls: [],
      llm_calls: [],
      error: null,
    },
    {
      seq: 2,
      node: "generate_visualization",
      status: "degraded",
      started_at: "2026-11-15T10:00:02Z",
      duration_ms: 90,
      summary: {},
      tool_calls: [{ tool: "validate_chart_spec", ok: true }],
      llm_calls: [],
      error: "LLMError: provider down",
    },
  ];

  it("maps node runs to timeline steps (degraded → recovered) with tools and details", () => {
    const steps = adaptTimeline(trace);
    expect(steps[0]).toMatchObject({
      node: "understand_query",
      label: "Understood the question",
      status: "succeeded",
      durationMs: 1200,
    });
    expect(steps[0]?.detail).toContain("intent: comparison");
    expect(steps[0]?.detail).toContain("metrics: 1");
    expect(steps[1]).toMatchObject({ status: "recovered", tools: ["validate_chart_spec"] });
    expect(steps[1]?.detail).toBe("LLMError: provider down");
  });

  it("describes what runs next", () => {
    expect(liveActivity([])).toBe("Starting the analysis…");
    expect(liveActivity(trace)).toBe("Drafting insights…");
  });
});
