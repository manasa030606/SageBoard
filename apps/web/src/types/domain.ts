/*
 * UI-side types for analysis results (timeline, SQL attempts, tables, charts, insights).
 * `features/analyst/live/adapt.ts` converts the API's snake_case responses
 * (`lib/api/types.ts`) into these.
 */

import type { WireChartType } from "@/lib/api/types";

export type ValueFormat = "currency" | "number" | "percent" | "integer";

export type ColumnType =
  "integer" | "bigint" | "numeric" | "boolean" | "date" | "timestamptz" | "text";
export type AgentNode =
  | "load_context"
  | "check_result"
  | "finish_step"
  | "recover_error"
  | "compose_response"
  | "understand_query"
  | "retrieve_schema"
  | "plan_analysis"
  | "generate_sql"
  | "validate_sql"
  | "execute_sql"
  | "analyze_results"
  | "generate_visualization"
  | "generate_insights"
  | "verify_insights"
  | "compose_report";

export interface TimelineStep {
  id: string;
  node: AgentNode;
  label: string;
  /** One line shown under the label once the step finishes. */
  detail: string;
  status: "succeeded" | "recovered" | "failed" | "skipped";
  durationMs: number;
  /** Tool calls made by the step (schema lookups, guard, executor…). */
  tools?: string[];
}

export interface SqlAttempt {
  attempt: number;
  sql: string;
  status: "accepted" | "rejected" | "failed";
  violations: { code: string; message: string }[];
  rowCount: number | null;
  execMs: number | null;
}

export interface ResultColumn {
  name: string;
  label: string;
  format: ValueFormat | "text" | "month";
}

export interface ResultTable {
  columns: ResultColumn[];
  rows: Array<Record<string, string | number>>;
  rowCount: number;
  truncated: boolean;
}

export interface ChartSpec {
  chartType: WireChartType;
  title: string;
  subtitle?: string;
  x: string;
  y: string[];
  valueFormat: ValueFormat;
}

export interface EvidenceRef {
  kind: "fact" | "rows";
  label: string;
  /** Row indices into the result table (for kind = rows). */
  rowIndices?: number[];
  value?: string;
  /** Live runs: which plan step's table the rows live in. */
  stepId?: string;
}

export interface Insight {
  id: string;
  category: "finding" | "comparison" | "anomaly" | "recommendation" | "caveat";
  headline: string;
  detail: string;
  confidence: "high" | "medium" | "low";
  evidence: EvidenceRef[];
}
