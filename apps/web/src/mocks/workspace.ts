/* DEMO DATA — Phase 2 only. History, conversations, reports, settings and usage. */
import type {
  Conversation,
  HistoryEntry,
  Report,
  SampleScenario,
  UsageSummary,
  UserSettings,
} from "@/types/domain";

import { SAMPLE_SCENARIOS } from "./scenarios";

function scenario(id: string): SampleScenario {
  const found = SAMPLE_SCENARIOS.find((s) => s.id === id);
  if (!found) throw new Error(`Unknown scenario ${id}`);
  return found;
}

function fromScenario(id: string, scenarioId: string, createdAt: string): HistoryEntry {
  const s = scenario(scenarioId);
  const accepted = s.result.sqlAttempts.find((a) => a.status === "accepted");
  return {
    id,
    question: s.question,
    datasetId: s.datasetId,
    status: s.outcome === "partial" ? "partial" : "succeeded",
    createdAt,
    durationMs: s.result.timeline.reduce((acc, t) => acc + t.durationMs, 0),
    queryCount: s.result.sqlAttempts.length,
    insightCount: s.result.insights.length,
    scenarioId,
    sql: accepted?.sql ?? null,
    rowCount: accepted?.rowCount ?? null,
    failureReason: s.failureReason ?? null,
  };
}

export const HISTORY: readonly HistoryEntry[] = [
  fromScenario("run_1048", "sc_regions", "2026-11-12T13:58:00Z"),
  fromScenario("run_1047", "sc_trend", "2026-11-12T11:20:00Z"),
  {
    id: "run_1046",
    question: "Which paid channel had the lowest cost per session in October?",
    datasetId: "ds_marketing_2026",
    status: "succeeded",
    createdAt: "2026-11-11T16:42:00Z",
    durationMs: 14_820,
    queryCount: 1,
    insightCount: 3,
    scenarioId: null,
    sql: `SELECT channel,
       ROUND(SUM(spend_usd) / NULLIF(SUM(sessions), 0), 3) AS cost_per_session
FROM marketing_spend_2026
WHERE week_start >= DATE '2026-10-01' AND week_start < DATE '2026-11-01'
GROUP BY channel
ORDER BY cost_per_session ASC
LIMIT 1001;`,
    rowCount: 6,
    failureReason: null,
  },
  fromScenario("run_1045", "sc_margin", "2026-11-11T10:05:00Z"),
  fromScenario("run_1044", "sc_products", "2026-11-10T15:31:00Z"),
  {
    id: "run_1043",
    question: "Show daily orders per store for every day since 2019",
    datasetId: "ds_retail_demo",
    status: "failed",
    createdAt: "2026-11-10T09:12:00Z",
    durationMs: 61_300,
    queryCount: 3,
    insightCount: 0,
    scenarioId: null,
    sql: null,
    rowCount: null,
    failureReason:
      "All 3 query attempts exceeded the 10-second limit. The data starts in Nov 2024 and has no store-level column; try asking for monthly orders by channel instead.",
  },
  fromScenario("run_1042", "sc_segments", "2026-11-09T14:47:00Z"),
  {
    id: "run_1041",
    question: "Compare weekly spend for Search and Social",
    datasetId: "ds_marketing_2026",
    status: "cancelled",
    createdAt: "2026-11-08T12:03:00Z",
    durationMs: 4_100,
    queryCount: 0,
    insightCount: 0,
    scenarioId: null,
    sql: null,
    rowCount: null,
    failureReason: "Cancelled by you during schema retrieval.",
  },
  {
    id: "run_1040",
    question: "How many orders were returned each month?",
    datasetId: "ds_retail_demo",
    status: "succeeded",
    createdAt: "2026-11-06T17:25:00Z",
    durationMs: 12_940,
    queryCount: 1,
    insightCount: 2,
    scenarioId: null,
    sql: `SELECT date_trunc('month', order_date)::date AS month,
       COUNT(*) FILTER (WHERE status = 'returned') AS returned_orders
FROM orders
GROUP BY 1
ORDER BY 1
LIMIT 1001;`,
    rowCount: 24,
    failureReason: null,
  },
];

export const CONVERSATIONS: readonly Conversation[] = [
  {
    id: "cv_regions",
    title: "Regional growth review",
    datasetId: "ds_retail_demo",
    updatedAt: "2026-11-12T13:58:00Z",
    runIds: ["run_1048"],
  },
  {
    id: "cv_trend",
    title: "Revenue trend for board pack",
    datasetId: "ds_retail_demo",
    updatedAt: "2026-11-12T11:20:00Z",
    runIds: ["run_1047"],
  },
  {
    id: "cv_margin",
    title: "Margin by category",
    datasetId: "ds_retail_demo",
    updatedAt: "2026-11-11T10:05:00Z",
    runIds: ["run_1045"],
  },
  {
    id: "cv_products",
    title: "Best sellers 2026",
    datasetId: "ds_retail_demo",
    updatedAt: "2026-11-10T15:31:00Z",
    runIds: ["run_1044"],
  },
  {
    id: "cv_segments",
    title: "Segment economics",
    datasetId: "ds_retail_demo",
    updatedAt: "2026-11-09T14:47:00Z",
    runIds: ["run_1042"],
  },
];

function reportFrom(
  id: string,
  scenarioId: string,
  runId: string,
  title: string,
  createdAt: string,
  tags: string[],
): Report {
  const s = scenario(scenarioId);
  const r = s.result;
  const accepted = r.sqlAttempts.find((a) => a.status === "accepted");
  const headline = r.insights.filter((i) => i.category !== "caveat");
  return {
    id,
    title,
    question: s.question,
    summary: headline
      .slice(0, 2)
      .map((i) => i.headline)
      .join(" "),
    datasetId: s.datasetId,
    datasetVersion: 3,
    runId,
    author: "Priya Raman",
    createdAt,
    updatedAt: createdAt,
    sections:
      r.chart && r.table
        ? [
            {
              heading: r.chart.title,
              body: r.restatedQuestion,
              chart: { spec: r.chart, table: r.table },
            },
          ]
        : [],
    insights: r.insights,
    limitations: [...r.limitations, ...r.assumptions.map((a) => `Assumption: ${a}`)],
    methodology: accepted
      ? [{ step: r.plan.map((p) => p.purpose).join(" "), sql: accepted.sql }]
      : [],
    tags,
  };
}

export const REPORTS: readonly Report[] = [
  reportFrom(
    "rp_regions_q3",
    "sc_regions",
    "run_1048",
    "Q3 2026 regional performance",
    "2026-11-12T14:05:00Z",
    ["Quarterly review", "Regions"],
  ),
  reportFrom(
    "rp_revenue_trend",
    "sc_trend",
    "run_1047",
    "Revenue trend — last 12 months",
    "2026-11-12T11:31:00Z",
    ["Board pack"],
  ),
  reportFrom(
    "rp_top_products",
    "sc_products",
    "run_1044",
    "Best-selling products, Jan–Oct 2026",
    "2026-11-10T15:44:00Z",
    ["Merchandising"],
  ),
  reportFrom(
    "rp_segments",
    "sc_segments",
    "run_1042",
    "Average order value by segment",
    "2026-11-09T15:02:00Z",
    ["Customers"],
  ),
];

export const USER_SETTINGS: UserSettings = {
  fullName: "Priya Raman",
  email: "priya@northwind-retail.example",
  role: "Business analyst",
  timezone: "Asia/Kolkata",
  clarificationMode: "ask",
  defaultRowLimit: 1000,
  autoCharts: true,
  showSqlByDefault: false,
  maskSensitiveColumns: true,
};

export const USAGE: UsageSummary = {
  runsToday: 7,
  runsLimit: 100,
  tokensMonth: 184_300,
  tokensLimit: 500_000,
  datasets: 4,
  storageBytes: 46_814_000,
  storageLimitBytes: 500_000_000,
};
