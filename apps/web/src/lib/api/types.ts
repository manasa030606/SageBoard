/*
 * Response and request shapes of the Sageboard API (mirrors app/schemas in apps/api).
 * Kept hand-written and small; the OpenAPI document at /api/v1/openapi.json is the
 * source of truth.
 */

export type ColumnType =
  "integer" | "bigint" | "numeric" | "boolean" | "date" | "timestamptz" | "text";

export const COLUMN_TYPES: readonly ColumnType[] = [
  "integer",
  "bigint",
  "numeric",
  "boolean",
  "date",
  "timestamptz",
  "text",
];

export interface Page<T> {
  items: T[];
  next_cursor: string | null;
}

// ---------------------------------------------------------------- auth
export interface User {
  id: string;
  email: string;
  full_name: string;
  created_at: string;
}

export interface SessionInfo {
  user: User;
  csrf_token: string;
  auth_mode: "session" | "demo";
}

// ------------------------------------------------------------ datasets
export type DatasetStatus = "pending_review" | "loading" | "ready" | "failed" | "deleting";

export interface DatasetSummary {
  id: string;
  name: string;
  description: string | null;
  source_type: "demo" | "upload_csv";
  file_name: string | null;
  status: DatasetStatus;
  status_reason: string | null;
  version: number;
  total_rows: number | null;
  size_bytes: number | null;
  table_count: number;
  created_at: string;
  updated_at: string;
}

export interface ColumnProfile {
  null_pct?: number;
  distinct_count?: number;
  min?: string | null;
  max?: string | null;
  top_values?: { value: string; count: number }[];
  examples?: string[];
}

export interface DatasetColumn {
  id: string;
  column_name: string;
  display_name: string;
  ordinal: number;
  data_type: ColumnType;
  inferred_type: ColumnType | null;
  is_nullable: boolean;
  is_primary_key: boolean;
  semantic_role: string | null;
  description: string | null;
  is_sensitive: boolean;
  profile: ColumnProfile;
}

export interface DatasetTable {
  id: string;
  table_name: string;
  display_name: string;
  description: string | null;
  row_count: number;
  primary_key: string[];
  columns: DatasetColumn[];
}

export interface DatasetDetail extends DatasetSummary {
  tables: DatasetTable[];
}

export interface UploadIssue {
  severity: "error" | "warning";
  code: string;
  message: string;
  column: string | null;
  line: number | null;
}

export interface InferredColumn {
  name: string;
  display_name: string;
  inferred_type: ColumnType;
  missing_count: number;
  sample_values: string[];
}

export interface UploadReview {
  dataset: DatasetSummary;
  row_count: number;
  rejected_count: number;
  rejected_samples: { line: number; reason: string }[];
  columns: InferredColumn[];
  issues: UploadIssue[];
}

export interface PreviewResponse {
  table: string;
  columns: { name: string; data_type: ColumnType; is_sensitive: boolean }[];
  rows: unknown[][];
  limit: number;
  offset: number;
  has_more: boolean;
  masked_columns: string[];
  exec_ms: number;
}

// -------------------------------------------------------------- history
export type ExecStatus = "not_run" | "ok" | "error" | "timeout" | "cancelled";
export type QueryOrigin = "agent" | "preview" | "widget_refresh" | "rerun";

export interface QueryHistoryItem {
  id: string;
  dataset_id: string;
  dataset_name: string;
  analysis_session_id: string | null;
  origin: QueryOrigin;
  attempt: number;
  executed_sql: string | null;
  guard_status: "accepted" | "rejected" | "not_applicable";
  guard_violations: { code: string; message: string }[];
  exec_status: ExecStatus;
  error_code: string | null;
  error_message: string | null;
  row_count: number | null;
  truncated: boolean;
  exec_ms: number | null;
  created_at: string;
}

export type SessionStatus =
  "queued" | "running" | "awaiting_input" | "succeeded" | "partial" | "failed" | "cancelled";

export interface SessionSummary {
  id: string;
  conversation_id: string;
  dataset_id: string;
  question: string;
  status: SessionStatus;
  duration_ms: number | null;
  created_at: string;
}

// -------------------------------------------------------------- reports
export interface ReportSummary {
  id: string;
  title: string;
  analysis_session_id: string | null;
  dataset_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ReportDetail extends ReportSummary {
  summary: string;
  summary_edited_by_user: boolean;
  content: {
    question?: string;
    status?: string;
    dataset?: { name: string | null; version: number };
    final_summary?: string | null;
    queries?: { sql: string; row_count: number | null; truncated: boolean }[];
    finished_at?: string | null;
  };
}

// -------------------------------------------- conversations & analysis sessions

export interface ConversationSummary {
  id: string;
  dataset_id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface MessageOut {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  analysis_session_id: string | null;
  created_at: string;
}

export interface ConversationDetail extends ConversationSummary {
  messages: MessageOut[];
  sessions: SessionSummary[];
}

export interface SessionAccepted {
  session: SessionSummary;
  agent_available: boolean;
  message: string;
}

export interface WireViolation {
  code: string;
  message: string;
}

export interface WireAttempt {
  attempt: number;
  sql: string;
  explanation: string;
  origin: "generation" | "recovery";
  guard_status: "pending" | "accepted" | "rejected";
  guard_violations: WireViolation[];
  normalized_sql: string | null;
  exec_status: ExecStatus;
  error_code: string | null;
  exec_error: string | null;
  exec_ms: number | null;
  row_count: number | null;
  diagnosis: { category: string; recoverable: boolean; summary: string; hint: string | null } | null;
}

export interface WireColumn {
  name: string;
  type: string;
}

export interface WireStep {
  step_id: string;
  purpose: string;
  expected_output: string;
  depends_on: string[];
  status: "pending" | "succeeded" | "failed" | "skipped";
  sql: string | null;
  explanation: string | null;
  attempts: WireAttempt[];
  columns: WireColumn[];
  row_count: number;
  truncated: boolean;
  rows: unknown[][];
  notes: string[];
  failure_explanation: string | null;
}

export type WireChartType =
  | "bar"
  | "grouped_bar"
  | "horizontal_bar"
  | "line"
  | "area"
  | "scatter"
  | "pie"
  | "donut"
  | "histogram"
  | "kpi"
  | "table";

export interface WireChart {
  chart_type: WireChartType;
  step_id: string;
  x: string | null;
  y: string[];
  series: string | null;
  title: string;
  subtitle: string | null;
  value_format: "number" | "currency" | "percent" | "integer";
  fallback_reason: string | null;
  data: unknown[][];
  columns: string[];
}

export interface WireEvidence {
  kind: "fact" | "cell";
  fact_id: string | null;
  step_id: string | null;
  row_index: number | null;
  column: string | null;
}

export interface WireInsight {
  insight_id: string;
  headline: string;
  detail: string;
  category: "finding" | "comparison" | "anomaly" | "recommendation" | "caveat";
  evidence: WireEvidence[];
  confidence: "high" | "medium" | "low";
  verification: "unverified" | "verified" | "rejected";
  rejection_reasons: string[];
}

export interface WireFact {
  fact_id: string;
  step_id: string;
  kind: string;
  description: string;
  value: unknown;
  unit: string | null;
  inputs: Record<string, unknown>;
}

export interface WireResponse {
  status: "answered" | "partial" | "clarification_needed" | "out_of_scope" | "failed";
  summary: string;
  key_findings: WireInsight[];
  caveats: string[];
  assumptions: string[];
  clarification_question: string | null;
  clarification_options: string[];
  follow_up_questions: string[];
  summary_source: "model" | "template";
}

export interface WireResult {
  response: WireResponse;
  steps: WireStep[];
  facts: WireFact[];
  charts: WireChart[];
  verification: {
    round: number;
    metrics_check: string;
    time_period_check: string;
    verified_insights: number;
    rejected_insights: number;
    removed: unknown[];
    uncertainty: string[];
  } | null;
  schema_tables: string[];
  budget: Record<string, number>;
  errors: string[];
  model: { provider: string; name: string };
}

export interface SessionDetail extends SessionSummary {
  dataset_version: number;
  termination_reason: string | null;
  understanding: {
    restated_question?: string;
    intent?: string;
    assumptions?: string[];
    time_range?: string | null;
  } | null;
  plan: { steps: { step_id: string; purpose: string }[] } | null;
  final_summary: string | null;
  error_code: string | null;
  error_message: string | null;
  llm_calls: number;
  sql_executions: number;
  tokens_in: number;
  tokens_out: number;
  started_at: string | null;
  finished_at: string | null;
  llm_provider: string | null;
  llm_model: string | null;
  result: WireResult | null;
}

export interface NodeRun {
  seq: number;
  node: string;
  status: "succeeded" | "failed" | "degraded";
  started_at: string;
  duration_ms: number;
  summary: Record<string, unknown>;
  tool_calls: { tool?: string; ok?: boolean; ms?: number }[];
  llm_calls: unknown[];
  error: string | null;
}
