"use client";

import { formatValue } from "@/lib/format";
import type { ChartSpec, ResultTable } from "@/types/domain";

import {
  BarChartView,
  LineChartView,
  PieChartView,
  ScatterChartView,
  type SeriesDef,
} from "./charts";
import { binValues } from "./histogram";

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
    case "pie":
    case "donut": {
      const y = spec.y[0];
      if (!y) return null;
      return (
        <PieChartView
          data={table.rows}
          x={spec.x}
          y={y}
          valueFormat={spec.valueFormat}
          donut={spec.chartType === "donut"}
          height={height}
          ariaLabel={aria}
        />
      );
    }
    case "scatter": {
      const y = spec.y[0];
      if (!y) return null;
      return (
        <ScatterChartView
          data={table.rows}
          x={spec.x}
          y={y}
          xLabel={label(spec.x)}
          yLabel={label(y)}
          valueFormat={spec.valueFormat}
          height={height}
          ariaLabel={aria}
        />
      );
    }
    case "histogram": {
      const y = spec.y[0];
      if (!y) return null;
      const bins = binValues(table.rows.map((row) => row[y]));
      return (
        <BarChartView
          data={bins.map((b) => ({ bin: b.bin, count: b.count }))}
          x="bin"
          series={[{ key: "count", label: `${label(y)} (rows)` }]}
          valueFormat="integer"
          height={height}
          ariaLabel={aria}
        />
      );
    }
    case "kpi": {
      const row = table.rows[0];
      if (!row) return null;
      return (
        <figure aria-label={aria} className="flex flex-wrap gap-8 px-2 py-4">
          {spec.y.map((key) => (
            <div key={key}>
              <p className="text-xs text-ink-2">{label(key)}</p>
              <p className="mt-1 font-mono text-[32px] leading-none font-medium text-ink tabular">
                {formatValue(Number(row[key] ?? 0), spec.valueFormat)}
              </p>
            </div>
          ))}
        </figure>
      );
    }
    default:
      return null;
  }
}
