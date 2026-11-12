"use client";

import type { ChartSpec, ResultTable } from "@/types/domain";

import { BarChartView, LineChartView, type SeriesDef } from "./charts";

/**
 * Renders an agent-produced ChartSpec. Only chart types in the spec enum are
 * supported; anything else falls back to the result table (rendered by the caller).
 */
export function ChartRenderer({
  spec,
  table,
  height = 300,
}: {
  spec: ChartSpec;
  table: ResultTable;
  height?: number;
}) {
  const label = (name: string) => table.columns.find((c) => c.name === name)?.label ?? name;
  const series: SeriesDef[] = spec.y.map((key, i) => ({
    key,
    label: label(key),
    // In two-series comparisons the first series is the earlier period → muted.
    muted:
      spec.y.length === 2 &&
      (key.startsWith("prev") || (spec.chartType === "grouped_bar" && i === 0)),
    color:
      spec.y.length === 2 && spec.chartType !== "line"
        ? i === 0
          ? "var(--color-sage-600)"
          : "var(--color-series-1)"
        : undefined,
  }));
  // Line charts: the current series should be drawn on top → render muted series first.
  const lineSeries = [...series].sort(
    (a, b) => Number(Boolean(b.muted)) - Number(Boolean(a.muted)),
  );
  const xColumn = table.columns.find((c) => c.name === spec.x);
  const aria = `${spec.title}${spec.subtitle ? `, ${spec.subtitle}` : ""}`;

  switch (spec.chartType) {
    case "line":
    case "area":
      return (
        <LineChartView
          data={table.rows}
          x={spec.x}
          series={lineSeries}
          valueFormat={spec.valueFormat}
          xFormat={xColumn?.format === "month" ? "month" : "text"}
          height={height}
          ariaLabel={aria}
        />
      );
    case "bar":
    case "grouped_bar":
      return (
        <BarChartView
          data={table.rows}
          x={spec.x}
          series={series.map((s) => ({ ...s, muted: false }))}
          valueFormat={spec.valueFormat}
          height={height}
          highlightIndex={spec.chartType === "bar" ? 0 : undefined}
          ariaLabel={aria}
        />
      );
    case "horizontal_bar":
      return (
        <BarChartView
          data={table.rows}
          x={spec.x}
          series={series}
          valueFormat={spec.valueFormat}
          layout="horizontal"
          height={Math.max(height, table.rows.length * 34 + 24)}
          highlightIndex={0}
          ariaLabel={aria}
        />
      );
    default:
      return null;
  }
}
