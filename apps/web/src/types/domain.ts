/*
 * Sageboard domain types used by the UI.
 *
 * Shapes mirror docs/API_SPECIFICATION.md (ChartSpec, Insight, EvidenceRef, run and
 * dataset models) so that replacing the mock data layer with the real API in later
 * phases does not change component props. Field names are camelCase on the client.
 */

// ------------------------------------------------------------------ analytics
export interface MonthlyMetric {
  /** ISO month, e.g. "2026-10". */
  month: string;
  revenue: number;
  orders: number;
  activeCustomers: number;
}

export interface RegionPerformance {
  region: string;
  revenue: number;
  orders: number;
  /** Quarter-over-quarter revenue growth as a fraction (0.08 = +8%). */
  growth: number;
}

export interface ProductPerformance {
  sku: string;
  name: string;
  category: string;
  unitsSold: number;
  revenue: number;
  growth: number;
}

export interface Kpi {
  key: "revenue" | "orders" | "customers" | "growth";
  label: string;
  value: number;
  format: ValueFormat;
  /** Change vs the comparison period as a fraction. */
  delta: number | null;
  comparisonLabel: string;
  sparkline: number[];
}

export interface DashboardSummary {
  periodLabel: string;
  datasetName: string;
  asOf: string;
  kpis: Kpi[];
  revenueTrend: { month: string; current: number; previous: number }[];
  regions: RegionPerformance[];
  topProducts: ProductPerformance[];
}

export type ValueFormat = "currency" | "number" | "percent" | "integer";

// ------------------------------------------------------------------- datasets
export type DatasetStatus = "pending_review" | "loading" | "ready" | "failed";
export type ColumnType =
  "integer" | "bigint" | "numeric" | "boolean" | "date" | "timestamptz" | "text";
export type SemanticRole = "identifier" | "measure" | "dimension" | "time" | "currency";

export interface ColumnProfile {
  nullPct: number;
  distinctCount: number;
  min: string | null;
  max: string | null;
  topValues: { value: string; count: number }[];
}

export interface DatasetColumn {
  name: string;
  displayName: string;
  type: ColumnType;
  semanticRole: SemanticRole | null;
  description: string | null;
  isSensitive: boolean;
  profile: ColumnProfile;
}

export interface DatasetTable {
  name: string;
  displayName: string;
  description: string | null;
  rowCount: number;
  columns: DatasetColumn[];
}

export interface Dataset {
  id: string;
  name: string;
  description: string;
  sourceType: "sample" | "upload_csv" | "upload_xlsx";
  fileName: string | null;
  status: DatasetStatus;
  statusReason: string | null;
  totalRows: number;
  sizeBytes: number;
  version: number;
  createdAt: string;
  updatedAt: string;
  tables: DatasetTable[];
}

// ----------------------------------------------------------------------- runs
export type RunStatus =
  "queued" | "running" | "awaiting_input" | "succeeded" | "partial" | "failed" | "cancelled";

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

export type StepStatus = "pending" | "running" | "succeeded" | "failed" | "recovered" | "skipped";

export interface TimelineStep {
  id: string;
  node: AgentNode;
  label: string;
  /** One line shown under the label once the step finishes. */
  detail: string;
  status: Exclude<StepStatus, "pending" | "running">;
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

export type ChartType =
  | "bar"
  | "grouped_bar"
  | "line"
  | "area"
  | "horizontal_bar"
  | "pie"
  | "donut"
  | "scatter"
  | "histogram"
  | "kpi"
  | "table";

export interface ChartSpec {
  chartType: ChartType;
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

export interface AnalysisPlanStep {
  id: string;
  purpose: string;
}

export interface RunResult {
  restatedQuestion: string;
  assumptions: string[];
  plan: AnalysisPlanStep[];
  timeline: TimelineStep[];
  sqlAttempts: SqlAttempt[];
  table: ResultTable | null;
  chart: ChartSpec | null;
  insights: Insight[];
  limitations: string[];
  usage: { llmCalls: number; sqlExecutions: number; tokens: number };
}

export interface Run {
  id: string;
  conversationId: string;
  datasetId: string;
  question: string;
  status: RunStatus;
  createdAt: string;
  durationMs: number | null;
  /** Present for completed runs; absent while queued. */
  result: RunResult | null;
  /** Plain-language failure reason for failed/partial runs. */
  failureReason?: string;
}

export interface Conversation {
  id: string;
  title: string;
  datasetId: string;
  updatedAt: string;
  runIds: string[];
}

/** A recorded sample run the workspace can replay in demo mode. */
export interface SampleScenario {
  id: string;
  question: string;
  shortLabel: string;
  datasetId: string;
  outcome: "succeeded" | "partial" | "failed";
  result: RunResult;
  failureReason?: string;
}

/** A row in query history. Sample-run entries link to their recorded scenario. */
export interface HistoryEntry {
  id: string;
  question: string;
  datasetId: string;
  status: RunStatus;
  createdAt: string;
  durationMs: number | null;
  queryCount: number;
  insightCount: number;
  scenarioId: string | null;
  sql: string | null;
  rowCount: number | null;
  failureReason: string | null;
}

// -------------------------------------------------------------------- reports
export interface ReportSection {
  heading: string;
  body: string;
  chart?: { spec: ChartSpec; table: ResultTable };
}

export interface Report {
  id: string;
  title: string;
  summary: string;
  question: string;
  datasetId: string;
  datasetVersion: number;
  runId: string;
  author: string;
  createdAt: string;
  updatedAt: string;
  sections: ReportSection[];
  insights: Insight[];
  limitations: string[];
  methodology: { step: string; sql: string }[];
  tags: string[];
}

// ------------------------------------------------------------------- settings
export interface UserSettings {
  fullName: string;
  email: string;
  role: string;
  timezone: string;
  clarificationMode: "ask" | "assume";
  defaultRowLimit: number;
  autoCharts: boolean;
  showSqlByDefault: boolean;
  maskSensitiveColumns: boolean;
}

export interface UsageSummary {
  runsToday: number;
  runsLimit: number;
  tokensMonth: number;
  tokensLimit: number;
  datasets: number;
  storageBytes: number;
  storageLimitBytes: number;
}
