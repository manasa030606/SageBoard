/*
 * Adapts live API shapes (SessionDetail, NodeRun) to the view models the analyst
 * components render. Pure functions, unit-tested.
 */
import type {
  NodeRun,
  SessionDetail,
  WireChart,
  WireFact,
  WireInsight,
  WireResult,
  WireStep,
} from "@/lib/api/types";
import type {
  AgentNode,
  ChartSpec,
  EvidenceRef,
  Insight,
  ResultColumn,
  ResultTable,
  SqlAttempt,
  TimelineStep,
} from "@/types/domain";

// ------------------------------------------------------------------ result tables

const INTEGER_TYPES = new Set(["int2", "int4", "int8", "integer", "bigint", "smallint"]);
const NUMERIC_TYPES = new Set(["numeric", "float4", "float8", "double precision", "money", "real"]);
const MIDNIGHT = /^(\d{4}-\d{2}-\d{2})T00:00:00(?:\.0+)?(?:Z|\+00:?00)$/;

export function columnLabel(name: string): string {
  const words = name.replaceAll("_", " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function columnFormat(pgType: string): ResultColumn["format"] {
  if (INTEGER_TYPES.has(pgType)) return "integer";
  if (NUMERIC_TYPES.has(pgType)) return "number";
  return "text";
}

function cell(value: unknown): string | number {
  if (typeof value === "number") return value;
  if (value === null || value === undefined) return "";
  if (typeof value === "boolean") return value ? "true" : "false";
  const text = String(value);
  const midnight = MIDNIGHT.exec(text);
  return midnight?.[1] ?? text;
}

export function toResultTable(
  columns: { name: string; type: string }[],
  rows: unknown[][],
  { rowCount, truncated }: { rowCount?: number; truncated?: boolean } = {},
): ResultTable {
  return {
    columns: columns.map((c) => ({
      name: c.name,
      label: columnLabel(c.name),
      format: columnFormat(c.type),
    })),
    rows: rows.map((row) => Object.fromEntries(columns.map((c, i) => [c.name, cell(row[i])]))),
    rowCount: rowCount ?? rows.length,
    truncated: truncated ?? false,
  };
}

// ------------------------------------------------------------------------ charts

export interface LiveChart {
  spec: ChartSpec;
  table: ResultTable | null;
  fallbackReason: string | null;
}

function chartTable(chart: WireChart, steps: WireStep[]): ResultTable | null {
  if (chart.data.length === 0 || chart.columns.length === 0) return null;
  const step = steps.find((s) => s.step_id === chart.step_id);
  const types = new Map((step?.columns ?? []).map((c) => [c.name, c.type]));
  return toResultTable(
    chart.columns.map((name) => ({ name, type: types.get(name) ?? "text" })),
    chart.data,
  );
}

export function adaptChart(chart: WireChart, steps: WireStep[]): LiveChart {
  return {
    spec: {
      chartType: chart.chart_type,
      title: chart.title,
      subtitle: chart.subtitle ?? undefined,
      x: chart.x ?? "",
      y: chart.y,
      valueFormat: chart.value_format,
    },
    table: chartTable(chart, steps),
    fallbackReason: chart.fallback_reason,
  };
}

// ---------------------------------------------------------------------- insights

const COMPACT = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });

function factValue(fact: WireFact): string {
  const { value } = fact;
  if (typeof value === "number") {
    const text = COMPACT.format(value);
    return fact.unit === "%" ? `${text}%` : fact.unit ? `${text} ${fact.unit}` : text;
  }
  if (Array.isArray(value)) return `${value.length} groups`;
  return value === null ? "—" : String(value).slice(0, 40);
}

function adaptEvidence(
  evidence: WireInsight["evidence"],
  facts: Map<string, WireFact>,
  steps: Map<string, WireStep>,
): EvidenceRef[] {
  return evidence.map((ref) => {
    if (ref.kind === "fact") {
      const fact = ref.fact_id ? facts.get(ref.fact_id) : undefined;
      return {
        kind: "fact",
        label: fact ? fact.description.slice(0, 80) : (ref.fact_id ?? "fact"),
        value: fact ? factValue(fact) : undefined,
      };
    }
    const step = ref.step_id ? steps.get(ref.step_id) : undefined;
    const rowIndices = ref.row_index === null ? [] : [ref.row_index];
    let value: string | undefined;
    if (step && ref.row_index !== null && ref.column) {
      const columnIndex = step.columns.findIndex((c) => c.name === ref.column);
      const raw = columnIndex >= 0 ? step.rows[ref.row_index]?.[columnIndex] : undefined;
      value =
        raw === undefined || raw === null
          ? undefined
          : typeof raw === "number"
            ? COMPACT.format(raw)
            : String(cell(raw)).slice(0, 40);
    }
    return {
      kind: "rows",
      label: ref.column ? columnLabel(ref.column) : `Row ${(ref.row_index ?? 0) + 1}`,
      rowIndices,
      value,
      stepId: ref.step_id ?? undefined,
    };
  });
}

export function adaptInsight(
  insight: WireInsight,
  facts: Map<string, WireFact>,
  steps: Map<string, WireStep>,
): Insight {
  return {
    id: insight.insight_id,
    category: insight.category,
    headline: insight.headline,
    detail: insight.detail,
    confidence: insight.confidence,
    evidence: adaptEvidence(insight.evidence, facts, steps),
  };
}

// ------------------------------------------------------------------------- steps

export interface LiveStep {
  id: string;
  purpose: string;
  status: WireStep["status"];
  sql: string | null;
  attempts: SqlAttempt[];
  table: ResultTable | null;
  notes: string[];
  failure: string | null;
}

function adaptAttempt(attempt: WireStep["attempts"][number]): SqlAttempt {
  const status =
    attempt.guard_status === "rejected"
      ? "rejected"
      : attempt.exec_status === "ok"
        ? "accepted"
        : "failed";
  return {
    attempt: attempt.attempt,
    sql: attempt.normalized_sql ?? attempt.sql,
    status,
    violations: attempt.guard_violations.map((v) => ({ code: v.code, message: v.message })),
    rowCount: attempt.row_count,
    execMs: attempt.exec_ms,
  };
}

export function adaptStep(step: WireStep): LiveStep {
  return {
    id: step.step_id,
    purpose: step.purpose,
    status: step.status,
    sql: step.sql,
    attempts: step.attempts.map(adaptAttempt),
    table:
      step.status === "succeeded"
        ? toResultTable(step.columns, step.rows, {
            rowCount: step.row_count,
            truncated: step.truncated,
          })
        : null,
    notes: step.notes,
    failure: step.failure_explanation,
  };
}

// ---------------------------------------------------------------------- timeline

const NODE_LABELS: Record<string, { node: AgentNode; label: string }> = {
  load_context: { node: "load_context", label: "Loaded the dataset catalog" },
  understand_query: { node: "understand_query", label: "Understood the question" },
  retrieve_schema: { node: "retrieve_schema", label: "Retrieved the schema" },
  plan_analysis: { node: "plan_analysis", label: "Planned the analysis" },
  generate_sql: { node: "generate_sql", label: "Wrote SQL" },
  validate_sql: { node: "validate_sql", label: "Validated SQL" },
  execute_sql: { node: "execute_sql", label: "Ran the query" },
  check_result: { node: "check_result", label: "Checked the result" },
  recover_error: { node: "recover_error", label: "Corrected the query" },
  finish_step: { node: "finish_step", label: "Closed the step" },
  analyze_results: { node: "analyze_results", label: "Analysed results" },
  generate_visualization: { node: "generate_visualization", label: "Chose charts" },
  generate_insights: { node: "generate_insights", label: "Drafted insights" },
  verify_insights: { node: "verify_insights", label: "Verified insights" },
  compose_response: { node: "compose_response", label: "Composed the answer" },
};

function summaryDetail(run: NodeRun): string {
  if (run.error) return run.error;
  const parts: string[] = [];
  for (const [key, value] of Object.entries(run.summary)) {
    if (value === null || value === undefined) continue;
    if (Array.isArray(value)) {
      if (value.length > 0) parts.push(`${key.replaceAll("_", " ")}: ${value.length}`);
    } else if (typeof value === "object") {
      continue;
    } else {
      parts.push(`${key.replaceAll("_", " ")}: ${String(value).slice(0, 60)}`);
    }
    if (parts.length === 3) break;
  }
  return parts.join(" · ");
}

export function adaptTimeline(trace: NodeRun[]): TimelineStep[] {
  return trace.map((run) => {
    const known = NODE_LABELS[run.node] ?? {
      node: "finish_step" as AgentNode,
      label: run.node.replaceAll("_", " "),
    };
    return {
      id: `n${run.seq}`,
      node: known.node,
      label: known.label,
      detail: summaryDetail(run),
      status:
        run.status === "succeeded"
          ? "succeeded"
          : run.status === "degraded"
            ? "recovered"
            : "failed",
      durationMs: run.duration_ms,
      tools: run.tool_calls
        .map((t) => t.tool)
        .filter((t): t is string => typeof t === "string")
        .slice(0, 6),
    };
  });
}

/** What the agent is doing right now, from the last completed node. */
export function liveActivity(trace: NodeRun[]): string {
  const last = trace.at(-1);
  if (!last) return "Starting the analysis…";
  const next: Partial<Record<string, string>> = {
    load_context: "Understanding the question…",
    understand_query: "Retrieving the schema…",
    retrieve_schema: "Planning the analysis…",
    plan_analysis: "Writing SQL…",
    generate_sql: "Validating SQL…",
    validate_sql: "Running the query…",
    execute_sql: "Checking the result…",
    check_result: "Continuing the plan…",
    recover_error: "Validating the corrected SQL…",
    finish_step: "Writing the next query…",
    analyze_results: "Choosing charts…",
    generate_visualization: "Drafting insights…",
    generate_insights: "Verifying insights…",
    verify_insights: "Composing the answer…",
  };
  return next[last.node] ?? "Finishing…";
}

// -------------------------------------------------------------------- whole runs

export interface LiveRun {
  status: SessionDetail["status"];
  question: string;
  summary: string | null;
  responseStatus: WireResult["response"]["status"] | null;
  restated: string | null;
  assumptions: string[];
  plan: { id: string; purpose: string }[];
  charts: LiveChart[];
  steps: LiveStep[];
  insights: Insight[];
  caveats: string[];
  followUps: string[];
  clarification: { question: string; options: string[] } | null;
  failureReason: string | null;
  usage: { llmCalls: number; sqlExecutions: number; tokens: number } | null;
  model: string | null;
  durationMs: number | null;
}

export function adaptRun(detail: SessionDetail): LiveRun {
  const result = detail.result;
  const response = result?.response ?? null;
  const steps = result?.steps ?? [];
  const factsById = new Map((result?.facts ?? []).map((f) => [f.fact_id, f]));
  const stepsById = new Map(steps.map((s) => [s.step_id, s]));
  const failed = detail.status === "failed" || detail.status === "cancelled";
  return {
    status: detail.status,
    question: detail.question,
    summary: response?.summary ?? detail.final_summary,
    responseStatus: response?.status ?? null,
    restated: detail.understanding?.restated_question ?? null,
    assumptions: response?.assumptions ?? detail.understanding?.assumptions ?? [],
    plan: (detail.plan?.steps ?? []).map((s) => ({ id: s.step_id, purpose: s.purpose })),
    charts: (result?.charts ?? []).map((c) => adaptChart(c, steps)),
    steps: steps.map(adaptStep),
    insights: (response?.key_findings ?? []).map((i) => adaptInsight(i, factsById, stepsById)),
    caveats: response?.caveats ?? [],
    followUps: response?.follow_up_questions ?? [],
    clarification:
      detail.status === "awaiting_input" && response?.clarification_question
        ? { question: response.clarification_question, options: response.clarification_options }
        : null,
    failureReason: failed ? (detail.error_message ?? response?.summary ?? null) : null,
    usage:
      detail.llm_calls > 0 || detail.sql_executions > 0
        ? {
            llmCalls: detail.llm_calls,
            sqlExecutions: detail.sql_executions,
            tokens: detail.tokens_in + detail.tokens_out,
          }
        : null,
    model: detail.llm_model ? `${detail.llm_provider}/${detail.llm_model}` : null,
    durationMs: detail.duration_ms,
  };
}
