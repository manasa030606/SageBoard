/*
 * DEMO DATA — Phase 2 only.
 *
 * Recorded sample runs the analyst workspace can replay so the interface can be
 * reviewed before the agent exists (Phase 5). They are labelled "Sample run" in
 * the UI and are never presented as answers to arbitrary questions.
 *
 * Result tables are computed from the demo series and every number in an insight
 * is formatted from those same rows, mirroring the real grounding rule.
 */
import {
  PERIODS,
  periodTotals,
  regionQuarterComparison,
  segmentPerformance,
  sum,
  topProducts,
} from "@/lib/data/analytics";
import { formatCurrency, formatMonth, formatPercent } from "@/lib/format";
import type { RunResult, SampleScenario, TimelineStep } from "@/types/domain";

const DATASET = "ds_retail_demo";

function step(
  id: string,
  node: TimelineStep["node"],
  label: string,
  detail: string,
  durationMs: number,
  extra: Partial<Pick<TimelineStep, "status" | "tools">> = {},
): TimelineStep {
  return {
    id,
    node,
    label,
    detail,
    durationMs,
    status: extra.status ?? "succeeded",
    tools: extra.tools,
  };
}

// --------------------------------------------------------------- 1. Revenue trend
function revenueTrend(): SampleScenario {
  const current = periodTotals("last12").months;
  const previous = periodTotals("previous12").months;
  const rows = current.map((m, i) => {
    const prev = previous[i]?.revenue ?? 0;
    return {
      month: m.month,
      revenue: m.revenue,
      prev_year_revenue: prev,
      yoy_growth: Math.round((m.revenue / prev - 1) * 10000) / 10000,
      orders: m.orders,
    };
  });
  const total = sum(rows.map((r) => r.revenue));
  const peakIndex = rows.reduce(
    (best, r, i) => (r.revenue > (rows[best]?.revenue ?? 0) ? i : best),
    0,
  );
  const peak = rows[peakIndex]!;
  const holiday = rows.filter((r) => r.month.endsWith("-11") || r.month.endsWith("-12"));
  const holidayShare = sum(holiday.map((r) => r.revenue)) / total;
  const lastIndex = rows.length - 1;
  const last = rows[lastIndex]!;
  const growths = rows.map((r) => r.yoy_growth);
  const minG = Math.min(...growths);
  const maxG = Math.max(...growths);
  const minRow = rows.findIndex((r) => r.yoy_growth === minG);
  const maxRow = rows.findIndex((r) => r.yoy_growth === maxG);

  const result: RunResult = {
    restatedQuestion:
      "Monthly revenue for the last 12 complete months, compared with the same month a year earlier.",
    assumptions: [
      "Revenue = quantity × unit price × (1 − discount) from order items.",
      "Cancelled orders are excluded.",
      "“Last 12 months” = Nov 2025 – Oct 2026 (November 2026 is still in progress).",
    ],
    plan: [
      {
        id: "s1",
        purpose:
          "Aggregate revenue and orders by month for 24 months and join each month to the same month one year earlier.",
      },
    ],
    timeline: [
      step(
        "t1",
        "understand_query",
        "Understood the question",
        "Trend · metric: revenue · grain: month · window: last 12 complete months",
        870,
      ),
      step(
        "t2",
        "retrieve_schema",
        "Retrieved schema",
        "orders, order_items · join on order_id · status values sampled",
        1380,
        {
          tools: [
            "get_table_schema(orders)",
            "get_table_schema(order_items)",
            "get_column_values(orders.status)",
          ],
        },
      ),
      step(
        "t3",
        "plan_analysis",
        "Planned the analysis",
        "1 step: monthly revenue with prior-year comparison",
        1040,
      ),
      step(
        "t4",
        "generate_sql",
        "Generated SQL · attempt 1",
        "Monthly aggregate over orders",
        2210,
      ),
      step(
        "t5",
        "validate_sql",
        "Validation rejected attempt 1",
        "UNKNOWN_COLUMN: orders.revenue does not exist",
        38,
        { status: "failed", tools: ["sql_guard.validate"] },
      ),
      step(
        "t6",
        "generate_sql",
        "Repaired SQL · attempt 2",
        "Computes revenue from order_items line totals",
        1960,
        { status: "recovered" },
      ),
      step(
        "t7",
        "validate_sql",
        "Validated SQL",
        "Read-only SELECT · 2 allow-listed tables · LIMIT 1001 applied · cost 4,812",
        41,
        {
          tools: ["sql_guard.validate", "explain_cost"],
        },
      ),
      step("t8", "execute_sql", "Executed query", "12 rows · 318 ms · read-only role", 318, {
        tools: ["executor.run"],
      }),
      step(
        "t9",
        "analyze_results",
        "Analysed results",
        "Computed total, peak month, seasonal share and YoY range",
        640,
        {
          tools: ["compute_total", "compute_rank", "compute_share", "compute_pct_change"],
        },
      ),
      step(
        "t10",
        "generate_visualization",
        "Chose a visualisation",
        "Line chart · revenue vs prior year",
        520,
      ),
      step("t11", "generate_insights", "Drafted insights", "4 insights from computed facts", 1890),
      step("t12", "verify_insights", "Verified insights", "4 of 4 grounded in result rows", 120, {
        tools: ["grounding.check"],
      }),
      step("t13", "compose_report", "Composed answer", "Summary, chart, table and caveats", 410),
    ],
    sqlAttempts: [
      {
        attempt: 1,
        status: "rejected",
        sql: `SELECT date_trunc('month', order_date)::date AS month,
       SUM(revenue) AS revenue
FROM orders
WHERE order_date >= DATE '2025-11-01'
GROUP BY 1
ORDER BY 1;`,
        violations: [
          {
            code: "UNKNOWN_COLUMN",
            message:
              "orders.revenue does not exist. Did you mean order_items.unit_price, order_items.quantity?",
          },
        ],
        rowCount: null,
        execMs: null,
      },
      {
        attempt: 2,
        status: "accepted",
        sql: `WITH monthly AS (
  SELECT date_trunc('month', o.order_date)::date AS month,
         SUM(oi.quantity * oi.unit_price * (1 - oi.discount)) AS revenue,
         COUNT(DISTINCT o.order_id) AS orders
  FROM orders AS o
  JOIN order_items AS oi ON oi.order_id = o.order_id
  WHERE o.status <> 'cancelled'
    AND o.order_date >= DATE '2024-11-01'
    AND o.order_date <  DATE '2026-11-01'
  GROUP BY 1
)
SELECT cur.month,
       ROUND(cur.revenue, 0)                      AS revenue,
       ROUND(prev.revenue, 0)                     AS prev_year_revenue,
       ROUND(cur.revenue / prev.revenue - 1, 4)   AS yoy_growth,
       cur.orders
FROM monthly AS cur
LEFT JOIN monthly AS prev
  ON prev.month = cur.month - INTERVAL '1 year'
WHERE cur.month >= DATE '2025-11-01'
ORDER BY cur.month
LIMIT 1001;`,
        violations: [],
        rowCount: rows.length,
        execMs: 318,
      },
    ],
    table: {
      columns: [
        { name: "month", label: "Month", format: "month" },
        { name: "revenue", label: "Revenue", format: "currency" },
        { name: "prev_year_revenue", label: "Prior year", format: "currency" },
        { name: "yoy_growth", label: "YoY", format: "percent" },
        { name: "orders", label: "Orders", format: "integer" },
      ],
      rows,
      rowCount: rows.length,
      truncated: false,
    },
    chart: {
      chartType: "line",
      title: "Monthly revenue",
      subtitle: `${PERIODS.last12.label} vs prior year`,
      x: "month",
      y: ["revenue", "prev_year_revenue"],
      valueFormat: "currency",
    },
    insights: [
      {
        id: "i1",
        category: "finding",
        headline: `Revenue peaked in ${formatMonth(peak.month, { withYear: true })} at ${formatCurrency(peak.revenue)}.`,
        detail: `November and December together brought in ${formatPercent(holidayShare)} of the 12-month total of ${formatCurrency(total)}.`,
        confidence: "high",
        evidence: [
          {
            kind: "rows",
            label: `${formatMonth(peak.month, { withYear: true })} row`,
            rowIndices: [peakIndex],
          },
          { kind: "fact", label: "12-month total", value: formatCurrency(total) },
        ],
      },
      {
        id: "i2",
        category: "comparison",
        headline: `${formatMonth(last.month, { withYear: true })} revenue was ${last.yoy_growth >= 0 ? "up" : "down"} ${formatPercent(Math.abs(last.yoy_growth))} year over year.`,
        detail: `${formatCurrency(last.revenue)} against ${formatCurrency(last.prev_year_revenue)} in ${formatMonth(previous[lastIndex]!.month, { withYear: true })}.`,
        confidence: "high",
        evidence: [
          {
            kind: "rows",
            label: `${formatMonth(last.month, { withYear: true })} row`,
            rowIndices: [lastIndex],
          },
        ],
      },
      {
        id: "i3",
        category: "finding",
        headline: "Every month grew compared with the year before.",
        detail: `Year-over-year growth ranged from ${formatPercent(minG, { signed: true })} (${formatMonth(rows[minRow]!.month, { withYear: true })}) to ${formatPercent(maxG, { signed: true })} (${formatMonth(rows[maxRow]!.month, { withYear: true })}).`,
        confidence: "high",
        evidence: [
          { kind: "rows", label: "Lowest and highest YoY rows", rowIndices: [minRow, maxRow] },
        ],
      },
      {
        id: "i4",
        category: "caveat",
        headline: "November 2026 is not included.",
        detail:
          "The dataset runs through 31 October 2026, so the current month would understate revenue.",
        confidence: "high",
        evidence: [{ kind: "fact", label: "orders.order_date max", value: "2026-10-31" }],
      },
    ],
    limitations: ["Revenue is gross of returns; 1,040 orders were later marked returned."],
    usage: { llmCalls: 9, sqlExecutions: 1, tokens: 18_420 },
  };

  return {
    id: "sc_trend",
    question: "How has monthly revenue trended over the last 12 months?",
    shortLabel: "Monthly revenue trend",
    datasetId: DATASET,
    outcome: "succeeded",
    result,
  };
}

// ---------------------------------------------------------- 2. Region growth
function regionGrowth(): SampleScenario {
  const rows = regionQuarterComparison().map((r) => ({
    region: r.region,
    q2_revenue: r.q2,
    q3_revenue: r.q3,
    growth: Math.round(r.growth * 10000) / 10000,
  }));
  const [first, second] = rows;
  const declining = rows.map((r, i) => ({ ...r, i })).filter((r) => r.growth < 0);
  const totalQ2 = sum(rows.map((r) => r.q2_revenue));
  const totalQ3 = sum(rows.map((r) => r.q3_revenue));
  const overall = totalQ3 / totalQ2 - 1;

  const result: RunResult = {
    restatedQuestion: "Revenue by region in Q2 2026 vs Q3 2026, ranked by growth.",
    assumptions: [
      "A region is the customer's home region.",
      "Q2 = Apr–Jun 2026, Q3 = Jul–Sep 2026.",
      "Cancelled orders are excluded.",
    ],
    plan: [
      {
        id: "s1",
        purpose:
          "Sum revenue per region for Q2 and Q3 2026 and compute quarter-over-quarter growth.",
      },
    ],
    timeline: [
      step(
        "t1",
        "understand_query",
        "Understood the question",
        "Ranking · metric: revenue growth · dimension: region · Q2 → Q3 2026",
        910,
      ),
      step(
        "t2",
        "retrieve_schema",
        "Retrieved schema",
        "orders, order_items, customers, regions · 3 join paths",
        1620,
        {
          tools: [
            "get_table_schema(orders)",
            "get_table_schema(regions)",
            "get_join_paths(orders, customers, regions)",
          ],
        },
      ),
      step(
        "t3",
        "plan_analysis",
        "Planned the analysis",
        "1 step: quarterly revenue per region with growth",
        980,
      ),
      step(
        "t4",
        "generate_sql",
        "Generated SQL · attempt 1",
        "Conditional aggregation by quarter",
        2380,
      ),
      step(
        "t5",
        "validate_sql",
        "Validated SQL",
        "Read-only SELECT · 4 allow-listed tables · cost 6,104",
        44,
        { tools: ["sql_guard.validate", "explain_cost"] },
      ),
      step(
        "t6",
        "execute_sql",
        "Database rejected attempt 1",
        "42803: column r.name must appear in the GROUP BY clause",
        96,
        { status: "failed", tools: ["executor.run"] },
      ),
      step(
        "t7",
        "generate_sql",
        "Repaired SQL · attempt 2",
        "Added r.name to GROUP BY using the database error",
        1710,
        { status: "recovered" },
      ),
      step("t8", "validate_sql", "Validated SQL", "Read-only SELECT · LIMIT 1001 applied", 39, {
        tools: ["sql_guard.validate", "explain_cost"],
      }),
      step("t9", "execute_sql", "Executed query", "6 rows · 402 ms", 402, {
        tools: ["executor.run"],
      }),
      step(
        "t10",
        "analyze_results",
        "Analysed results",
        "Ranked regions, computed overall growth",
        580,
        { tools: ["compute_pct_change", "compute_rank"] },
      ),
      step(
        "t11",
        "generate_visualization",
        "Chose a visualisation",
        "Grouped bars · Q2 vs Q3 by region",
        470,
      ),
      step("t12", "generate_insights", "Drafted insights", "5 insights from computed facts", 1720),
      step(
        "t13",
        "verify_insights",
        "Verified insights",
        "4 verified · 1 removed (unsupported cause)",
        140,
        { tools: ["grounding.check"] },
      ),
      step("t14", "compose_report", "Composed answer", "Summary, chart, table and caveats", 390),
    ],
    sqlAttempts: [
      {
        attempt: 1,
        status: "failed",
        sql: `SELECT r.name AS region,
       SUM(oi.quantity * oi.unit_price * (1 - oi.discount))
         FILTER (WHERE o.order_date >= DATE '2026-04-01' AND o.order_date < DATE '2026-07-01') AS q2_revenue,
       SUM(oi.quantity * oi.unit_price * (1 - oi.discount))
         FILTER (WHERE o.order_date >= DATE '2026-07-01' AND o.order_date < DATE '2026-10-01') AS q3_revenue
FROM orders AS o
JOIN order_items AS oi ON oi.order_id = o.order_id
JOIN customers  AS c  ON c.customer_id = o.customer_id
JOIN regions    AS r  ON r.region_id = c.region_id
WHERE o.status <> 'cancelled'
GROUP BY r.region_id;`,
        violations: [
          {
            code: "42803",
            message:
              'column "r.name" must appear in the GROUP BY clause or be used in an aggregate function',
          },
        ],
        rowCount: null,
        execMs: 96,
      },
      {
        attempt: 2,
        status: "accepted",
        sql: `WITH quarterly AS (
  SELECT r.name AS region,
         SUM(oi.quantity * oi.unit_price * (1 - oi.discount))
           FILTER (WHERE o.order_date >= DATE '2026-04-01' AND o.order_date < DATE '2026-07-01') AS q2_revenue,
         SUM(oi.quantity * oi.unit_price * (1 - oi.discount))
           FILTER (WHERE o.order_date >= DATE '2026-07-01' AND o.order_date < DATE '2026-10-01') AS q3_revenue
  FROM orders AS o
  JOIN order_items AS oi ON oi.order_id = o.order_id
  JOIN customers  AS c  ON c.customer_id = o.customer_id
  JOIN regions    AS r  ON r.region_id = c.region_id
  WHERE o.status <> 'cancelled'
  GROUP BY r.region_id, r.name
)
SELECT region,
       ROUND(q2_revenue, 0)                   AS q2_revenue,
       ROUND(q3_revenue, 0)                   AS q3_revenue,
       ROUND(q3_revenue / q2_revenue - 1, 4)  AS growth
FROM quarterly
ORDER BY growth DESC
LIMIT 1001;`,
        violations: [],
        rowCount: rows.length,
        execMs: 402,
      },
    ],
    table: {
      columns: [
        { name: "region", label: "Region", format: "text" },
        { name: "q2_revenue", label: "Q2 2026", format: "currency" },
        { name: "q3_revenue", label: "Q3 2026", format: "currency" },
        { name: "growth", label: "Growth", format: "percent" },
      ],
      rows,
      rowCount: rows.length,
      truncated: false,
    },
    chart: {
      chartType: "grouped_bar",
      title: "Revenue by region",
      subtitle: "Q2 vs Q3 2026",
      x: "region",
      y: ["q2_revenue", "q3_revenue"],
      valueFormat: "currency",
    },
    insights: [
      {
        id: "i1",
        category: "finding",
        headline: `${first!.region} grew fastest at ${formatPercent(first!.growth, { signed: true })}.`,
        detail: `Revenue rose from ${formatCurrency(first!.q2_revenue)} to ${formatCurrency(first!.q3_revenue)}, followed by ${second!.region} at ${formatPercent(second!.growth, { signed: true })}.`,
        confidence: "high",
        evidence: [
          {
            kind: "rows",
            label: `${first!.region} and ${second!.region} rows`,
            rowIndices: [0, 1],
          },
        ],
      },
      ...declining.map((d) => ({
        id: `i-decline-${d.i}`,
        category: "anomaly" as const,
        headline: `${d.region} was the only region to decline (${formatPercent(d.growth, { signed: true })}).`,
        detail: `${formatCurrency(d.q3_revenue)} in Q3 against ${formatCurrency(d.q2_revenue)} in Q2, while overall revenue grew ${formatPercent(overall, { signed: true })}.`,
        confidence: "high" as const,
        evidence: [
          { kind: "rows" as const, label: `${d.region} row`, rowIndices: [d.i] },
          {
            kind: "fact" as const,
            label: "Overall Q2 → Q3 growth",
            value: formatPercent(overall, { signed: true }),
          },
        ],
      })),
      {
        id: "i3",
        category: "recommendation",
        headline: `Worth investigating what changed in ${declining[0]?.region ?? "the weakest region"} during Q3.`,
        detail:
          "The data shows the decline but not its cause. Comparing channel mix or product mix for that region would be a useful next question.",
        confidence: "medium",
        evidence: [
          { kind: "rows", label: "Declining region row", rowIndices: declining.map((d) => d.i) },
        ],
      },
      {
        id: "i4",
        category: "caveat",
        headline: `${first!.region} starts from the smallest base.`,
        detail:
          "High growth on a small revenue base moves less absolute revenue than modest growth in larger regions.",
        confidence: "medium",
        evidence: [{ kind: "rows", label: `${first!.region} row`, rowIndices: [0] }],
      },
    ],
    limitations: [
      "One drafted insight claimed a cause for the Midwest decline; it was removed because no result supports a cause.",
    ],
    usage: { llmCalls: 11, sqlExecutions: 2, tokens: 22_960 },
  };

  return {
    id: "sc_regions",
    question: "Which regions grew revenue fastest from Q2 to Q3 2026?",
    shortLabel: "Regional growth Q2 → Q3",
    datasetId: DATASET,
    outcome: "succeeded",
    result,
  };
}

// --------------------------------------------------------- 3. Top products
function productRanking(): SampleScenario {
  const products = topProducts();
  const rows = products.map((p, i) => ({
    rank: i + 1,
    product: p.name,
    category: p.category,
    units: p.unitsSold,
    revenue: p.revenue,
    growth: p.growth,
  }));
  const top10 = sum(rows.map((r) => r.revenue));
  const ytd = periodTotals("ytd").revenue;
  const home = rows.map((r, i) => ({ ...r, i })).filter((r) => r.category === "Home");
  const homeShare = sum(home.map((r) => r.revenue)) / top10;
  const fastest = rows.reduce((best, r) => (r.growth > best.growth ? r : best), rows[0]!);
  const fastestIndex = rows.indexOf(fastest);
  const shrinking = rows.map((r, i) => ({ ...r, i })).filter((r) => r.growth < 0);

  const result: RunResult = {
    restatedQuestion: "The 10 products with the highest revenue from January to October 2026.",
    assumptions: [
      "“This year” = 1 Jan – 31 Oct 2026 (latest complete data).",
      "Growth compares the same months of 2025.",
    ],
    plan: [
      { id: "s1", purpose: "Rank products by year-to-date revenue and units sold." },
      { id: "s2", purpose: "Compute growth against the same period last year for the top 10." },
    ],
    timeline: [
      step(
        "t1",
        "understand_query",
        "Understood the question",
        "Ranking · metric: revenue · dimension: product · top 10 · YTD 2026",
        820,
      ),
      step("t2", "retrieve_schema", "Retrieved schema", "order_items, products, orders", 1210, {
        tools: ["get_table_schema(products)", "get_table_schema(order_items)"],
      }),
      step(
        "t3",
        "plan_analysis",
        "Planned the analysis",
        "2 steps: rank, then compare with 2025",
        1130,
      ),
      step("t4", "generate_sql", "Generated SQL", "Single query with two period aggregates", 2470),
      step("t5", "validate_sql", "Validated SQL", "Read-only SELECT · LIMIT 10 · cost 3,377", 36, {
        tools: ["sql_guard.validate", "explain_cost"],
      }),
      step("t6", "execute_sql", "Executed query", "10 rows · 276 ms", 276, {
        tools: ["executor.run"],
      }),
      step(
        "t7",
        "analyze_results",
        "Analysed results",
        "Shares of top-10 revenue, category concentration, growth extremes",
        610,
        {
          tools: ["compute_share", "compute_rank"],
        },
      ),
      step(
        "t8",
        "generate_visualization",
        "Chose a visualisation",
        "Horizontal bars · revenue by product",
        430,
      ),
      step("t9", "generate_insights", "Drafted insights", "4 insights", 1650),
      step("t10", "verify_insights", "Verified insights", "4 of 4 grounded", 110, {
        tools: ["grounding.check"],
      }),
      step("t11", "compose_report", "Composed answer", "Summary, chart, table", 360),
    ],
    sqlAttempts: [
      {
        attempt: 1,
        status: "accepted",
        sql: `WITH sales AS (
  SELECT p.product_id, p.name AS product, p.category,
         SUM(oi.quantity) FILTER (WHERE o.order_date >= DATE '2026-01-01') AS units,
         SUM(oi.quantity * oi.unit_price * (1 - oi.discount))
           FILTER (WHERE o.order_date >= DATE '2026-01-01') AS revenue,
         SUM(oi.quantity * oi.unit_price * (1 - oi.discount))
           FILTER (WHERE o.order_date >= DATE '2025-01-01'
                     AND o.order_date <  DATE '2025-11-01') AS revenue_2025
  FROM order_items AS oi
  JOIN orders   AS o ON o.order_id = oi.order_id
  JOIN products AS p ON p.product_id = oi.product_id
  WHERE o.status <> 'cancelled'
    AND o.order_date >= DATE '2025-01-01'
    AND o.order_date <  DATE '2026-11-01'
    AND (o.order_date < DATE '2025-11-01' OR o.order_date >= DATE '2026-01-01')
  GROUP BY p.product_id, p.name, p.category
)
SELECT RANK() OVER (ORDER BY revenue DESC) AS rank,
       product, category, units,
       ROUND(revenue, 0)                   AS revenue,
       ROUND(revenue / revenue_2025 - 1, 4) AS growth
FROM sales
ORDER BY revenue DESC
LIMIT 10;`,
        violations: [],
        rowCount: rows.length,
        execMs: 276,
      },
    ],
    table: {
      columns: [
        { name: "rank", label: "#", format: "integer" },
        { name: "product", label: "Product", format: "text" },
        { name: "category", label: "Category", format: "text" },
        { name: "units", label: "Units", format: "integer" },
        { name: "revenue", label: "Revenue", format: "currency" },
        { name: "growth", label: "vs 2025", format: "percent" },
      ],
      rows,
      rowCount: rows.length,
      truncated: false,
    },
    chart: {
      chartType: "horizontal_bar",
      title: "Top 10 products by revenue",
      subtitle: PERIODS.ytd.label,
      x: "product",
      y: ["revenue"],
      valueFormat: "currency",
    },
    insights: [
      {
        id: "i1",
        category: "finding",
        headline: `${rows[0]!.product} leads with ${formatCurrency(rows[0]!.revenue)}.`,
        detail: `That is ${formatPercent(rows[0]!.revenue / top10)} of top-10 revenue, which itself is ${formatPercent(top10 / ytd)} of all revenue so far this year (${formatCurrency(ytd)}).`,
        confidence: "high",
        evidence: [
          { kind: "rows", label: "Rank 1 row", rowIndices: [0] },
          { kind: "fact", label: "Year-to-date revenue", value: formatCurrency(ytd) },
        ],
      },
      {
        id: "i2",
        category: "finding",
        headline: `Home products take ${home.length} of the top 10 spots.`,
        detail: `Together they account for ${formatPercent(homeShare)} of top-10 revenue.`,
        confidence: "high",
        evidence: [{ kind: "rows", label: "Home category rows", rowIndices: home.map((h) => h.i) }],
      },
      {
        id: "i3",
        category: "comparison",
        headline: `${fastest.product} is growing fastest (${formatPercent(fastest.growth, { signed: true })}).`,
        detail: `${shrinking.map((s) => s.product).join(" and ")} sold less than in the same period of 2025.`,
        confidence: "high",
        evidence: [
          { kind: "rows", label: `${fastest.product} row`, rowIndices: [fastestIndex] },
          { kind: "rows", label: "Declining products", rowIndices: shrinking.map((s) => s.i) },
        ],
      },
      {
        id: "i4",
        category: "caveat",
        headline: "Growth compares ten months with ten months.",
        detail:
          "November and December are excluded from both years, so holiday sales are not reflected yet.",
        confidence: "high",
        evidence: [
          { kind: "fact", label: "Comparison window", value: "Jan–Oct 2025 vs Jan–Oct 2026" },
        ],
      },
    ],
    limitations: [],
    usage: { llmCalls: 8, sqlExecutions: 1, tokens: 16_210 },
  };

  return {
    id: "sc_products",
    question: "What are our top 10 products by revenue this year?",
    shortLabel: "Top 10 products",
    datasetId: DATASET,
    outcome: "succeeded",
    result,
  };
}

// ---------------------------------------------------------- 4. Segment AOV
function segmentAov(): SampleScenario {
  const rows = segmentPerformance().map((s) => ({
    segment: s.segment,
    orders: s.orders,
    revenue: s.revenue,
    aov: s.aov,
  }));
  const top = rows[0]!;
  const bottom = rows[rows.length - 1]!;
  const totalOrders = sum(rows.map((r) => r.orders));
  const totalRevenue = sum(rows.map((r) => r.revenue));
  const consumerIndex = rows.findIndex((r) => r.segment === "Consumer");
  const consumer = rows[consumerIndex]!;

  const result: RunResult = {
    restatedQuestion: "Average order value by customer segment over the last 12 months.",
    assumptions: [
      "Average order value = revenue ÷ number of orders.",
      `Period: ${PERIODS.last12.label}.`,
    ],
    plan: [
      {
        id: "s1",
        purpose:
          "Aggregate orders and revenue by customer segment and compute average order value.",
      },
    ],
    timeline: [
      step(
        "t1",
        "understand_query",
        "Understood the question",
        "Comparison · metric: average order value · dimension: segment",
        760,
      ),
      step(
        "t2",
        "retrieve_schema",
        "Retrieved schema",
        "orders, order_items, customers · segment values sampled",
        1290,
        {
          tools: ["get_table_schema(customers)", "get_column_values(customers.segment)"],
        },
      ),
      step("t3", "plan_analysis", "Planned the analysis", "1 step: AOV per segment", 870),
      step("t4", "generate_sql", "Generated SQL", "Revenue ÷ distinct orders per segment", 1930),
      step(
        "t5",
        "validate_sql",
        "Validated SQL",
        "Read-only SELECT · sensitive column customers.email not referenced",
        37,
        {
          tools: ["sql_guard.validate", "explain_cost"],
        },
      ),
      step("t6", "execute_sql", "Executed query", "3 rows · 241 ms", 241, {
        tools: ["executor.run"],
      }),
      step(
        "t7",
        "analyze_results",
        "Analysed results",
        "AOV ratio, order and revenue shares",
        520,
        { tools: ["compute_share", "compute_rank"] },
      ),
      step("t8", "generate_visualization", "Chose a visualisation", "Bars · AOV by segment", 380),
      step("t9", "generate_insights", "Drafted insights", "3 insights", 1420),
      step("t10", "verify_insights", "Verified insights", "3 of 3 grounded", 90, {
        tools: ["grounding.check"],
      }),
      step("t11", "compose_report", "Composed answer", "Summary, chart, table", 330),
    ],
    sqlAttempts: [
      {
        attempt: 1,
        status: "accepted",
        sql: `SELECT c.segment,
       COUNT(DISTINCT o.order_id)                                       AS orders,
       ROUND(SUM(oi.quantity * oi.unit_price * (1 - oi.discount)), 0)  AS revenue,
       ROUND(SUM(oi.quantity * oi.unit_price * (1 - oi.discount))
             / COUNT(DISTINCT o.order_id), 2)                          AS aov
FROM orders AS o
JOIN order_items AS oi ON oi.order_id = o.order_id
JOIN customers   AS c  ON c.customer_id = o.customer_id
WHERE o.status <> 'cancelled'
  AND o.order_date >= DATE '2025-11-01'
  AND o.order_date <  DATE '2026-11-01'
GROUP BY c.segment
ORDER BY aov DESC
LIMIT 1001;`,
        violations: [],
        rowCount: rows.length,
        execMs: 241,
      },
    ],
    table: {
      columns: [
        { name: "segment", label: "Segment", format: "text" },
        { name: "orders", label: "Orders", format: "integer" },
        { name: "revenue", label: "Revenue", format: "currency" },
        { name: "aov", label: "Avg order value", format: "currency" },
      ],
      rows,
      rowCount: rows.length,
      truncated: false,
    },
    chart: {
      chartType: "bar",
      title: "Average order value by segment",
      subtitle: PERIODS.last12.label,
      x: "segment",
      y: ["aov"],
      valueFormat: "currency",
    },
    insights: [
      {
        id: "i1",
        category: "comparison",
        headline: `${top.segment} orders are the largest, at ${formatCurrency(top.aov, { cents: true })} on average.`,
        detail: `That is ${(top.aov / bottom.aov).toFixed(1)}× the ${bottom.segment} average of ${formatCurrency(bottom.aov, { cents: true })}.`,
        confidence: "high",
        evidence: [
          {
            kind: "rows",
            label: `${top.segment} and ${bottom.segment} rows`,
            rowIndices: [0, rows.length - 1],
          },
        ],
      },
      {
        id: "i2",
        category: "finding",
        headline: `Consumer customers place ${formatPercent(consumer.orders / totalOrders, { digits: 0 })} of orders but ${formatPercent(consumer.revenue / totalRevenue, { digits: 0 })} of revenue.`,
        detail: `${consumer.orders.toLocaleString("en-US")} of ${totalOrders.toLocaleString("en-US")} orders and ${formatCurrency(consumer.revenue)} of ${formatCurrency(totalRevenue)}.`,
        confidence: "high",
        evidence: [{ kind: "rows", label: "Consumer row", rowIndices: [consumerIndex] }],
      },
      {
        id: "i3",
        category: "recommendation",
        headline: `Consider whether ${top.segment.toLowerCase()} accounts warrant dedicated account management.`,
        detail:
          "Few orders with high value make each account matter more. Retention data would be needed to confirm this.",
        confidence: "low",
        evidence: [{ kind: "rows", label: `${top.segment} row`, rowIndices: [0] }],
      },
    ],
    limitations: [
      "Segments come from the customer record at query time; customers who changed segment are counted in their current one.",
    ],
    usage: { llmCalls: 8, sqlExecutions: 1, tokens: 14_380 },
  };

  return {
    id: "sc_segments",
    question: "Which customer segment has the highest average order value?",
    shortLabel: "AOV by segment",
    datasetId: DATASET,
    outcome: "succeeded",
    result,
  };
}

// ---------------------------------------------- 5. Not answerable from data
function profitMargin(): SampleScenario {
  return {
    id: "sc_margin",
    question: "What is our profit margin by product category?",
    shortLabel: "Profit margin (not answerable)",
    datasetId: DATASET,
    outcome: "partial",
    failureReason:
      "This dataset has no product cost, COGS or margin columns, so profit margin can’t be calculated. Sageboard stopped before writing SQL rather than estimate it.",
    result: {
      restatedQuestion:
        "Profit margin (revenue minus cost, as a share of revenue) per product category.",
      assumptions: [],
      plan: [],
      timeline: [
        step(
          "t1",
          "understand_query",
          "Understood the question",
          "Composition · metric: profit margin · dimension: category",
          840,
        ),
        step(
          "t2",
          "retrieve_schema",
          "Searched the schema",
          "No cost, COGS or margin column in any of 5 tables",
          1730,
          {
            status: "failed",
            tools: [
              "get_table_schema(products)",
              "get_table_schema(order_items)",
              "search_columns(cost|cogs|margin)",
            ],
          },
        ),
        step("t3", "plan_analysis", "Skipped planning", "Stopped: required data is missing", 0, {
          status: "skipped",
        }),
        step(
          "t4",
          "compose_report",
          "Explained the limitation",
          "Suggested answerable alternatives",
          520,
        ),
      ],
      sqlAttempts: [],
      table: null,
      chart: null,
      insights: [],
      limitations: [
        "Revenue by category is available; cost is not.",
        "Upload a product cost file (product_id, unit_cost) to enable margin analysis.",
      ],
      usage: { llmCalls: 3, sqlExecutions: 0, tokens: 5_120 },
    },
  };
}

export const SAMPLE_SCENARIOS: readonly SampleScenario[] = [
  revenueTrend(),
  regionGrowth(),
  productRanking(),
  segmentAov(),
  profitMargin(),
];
