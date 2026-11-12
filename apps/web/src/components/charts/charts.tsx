"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
} from "recharts";

import { formatMonth, formatValue } from "@/lib/format";
import type { ValueFormat } from "@/types/domain";

/*
 * Chart building blocks. One axis style, one tooltip and one palette so every
 * chart in the product reads as the same system.
 */
export const SERIES_COLORS = [
  "var(--color-series-1)",
  "var(--color-series-2)",
  "var(--color-series-3)",
  "var(--color-series-4)",
  "var(--color-series-5)",
];

export interface SeriesDef {
  key: string;
  label: string;
  color?: string;
  /** Muted, dashed rendering for comparison series (e.g. prior year). */
  muted?: boolean;
}

type Row = Record<string, string | number>;

const tick = { fontSize: 11, fontFamily: "var(--font-mono)", fill: "var(--color-ink-2)" };

function formatX(value: unknown, xFormat: "month" | "text"): string {
  const s = String(value);
  return xFormat === "month" ? formatMonth(s) : s;
}

function ChartTooltip({
  active,
  payload,
  label,
  valueFormat,
  xFormat,
}: TooltipContentProps & { valueFormat: ValueFormat; xFormat: "month" | "text" }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="min-w-40 rounded-sm border border-line bg-paper px-3 py-2 shadow-overlay">
      <p className="mb-1.5 text-xs font-medium text-ink">
        {xFormat === "month" ? formatMonth(String(label), { withYear: true }) : String(label)}
      </p>
      <ul className="grid gap-1">
        {payload.map((entry) => (
          <li
            key={String(entry.dataKey)}
            className="flex items-center justify-between gap-4 text-xs"
          >
            <span className="flex items-center gap-1.5 text-ink-2">
              <span aria-hidden className="size-2 rounded-xs" style={{ background: entry.color }} />
              {entry.name}
            </span>
            <span className="font-mono text-ink tabular">
              {formatValue(Number(entry.value), valueFormat)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function LegendRow({ series }: { series: SeriesDef[] }) {
  if (series.length < 2) return null;
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 pl-1 text-xs text-ink-2">
      {series.map((s, i) => (
        <li key={s.key} className="flex items-center gap-1.5">
          <span
            aria-hidden
            className="inline-block h-0.5 w-3.5"
            style={{
              background: s.color ?? SERIES_COLORS[i],
              opacity: s.muted ? 0.55 : 1,
            }}
          />
          {s.label}
        </li>
      ))}
    </ul>
  );
}

export function LineChartView({
  data,
  x,
  series,
  valueFormat,
  xFormat = "month",
  height = 280,
  ariaLabel,
}: {
  data: Row[];
  x: string;
  series: SeriesDef[];
  valueFormat: ValueFormat;
  xFormat?: "month" | "text";
  height?: number;
  ariaLabel: string;
}) {
  return (
    <figure aria-label={ariaLabel} className="grid gap-3">
      <LegendRow series={series} />
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart
            data={data}
            margin={{ top: 8, right: 12, bottom: 0, left: 0 }}
            accessibilityLayer
          >
            <CartesianGrid stroke="var(--color-line)" strokeDasharray="0" vertical={false} />
            <XAxis
              dataKey={x}
              tick={tick}
              tickLine={false}
              axisLine={{ stroke: "var(--color-line-strong)" }}
              tickFormatter={(v) => formatX(v, xFormat)}
              tickMargin={8}
              interval="preserveStartEnd"
              minTickGap={18}
            />
            <YAxis
              tick={tick}
              tickLine={false}
              axisLine={false}
              width={64}
              tickFormatter={(v: number) => formatValue(v, valueFormat, { compact: true })}
            />
            <Tooltip
              cursor={{ stroke: "var(--color-line-strong)", strokeWidth: 1 }}
              content={(props) => (
                <ChartTooltip {...props} valueFormat={valueFormat} xFormat={xFormat} />
              )}
            />
            {series.map((s, i) => (
              <Line
                key={s.key}
                type="monotone"
                dataKey={s.key}
                name={s.label}
                stroke={s.color ?? SERIES_COLORS[i]}
                strokeWidth={s.muted ? 1.5 : 2}
                strokeOpacity={s.muted ? 0.55 : 1}
                strokeDasharray={s.muted ? "4 4" : undefined}
                dot={false}
                activeDot={{ r: 3.5, strokeWidth: 0 }}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </figure>
  );
}

export function BarChartView({
  data,
  x,
  series,
  valueFormat,
  layout = "vertical",
  height = 280,
  highlightIndex,
  ariaLabel,
}: {
  data: Row[];
  x: string;
  series: SeriesDef[];
  valueFormat: ValueFormat;
  /** "vertical" = upright columns; "horizontal" = bars growing to the right. */
  layout?: "vertical" | "horizontal";
  height?: number;
  highlightIndex?: number;
  ariaLabel: string;
}) {
  const horizontal = layout === "horizontal";
  const single = series.length === 1;
  return (
    <figure aria-label={ariaLabel} className="grid gap-3">
      <LegendRow series={series} />
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={data}
            layout={horizontal ? "vertical" : "horizontal"}
            margin={{ top: 8, right: 16, bottom: 0, left: horizontal ? 8 : 0 }}
            barCategoryGap={horizontal ? "22%" : "28%"}
            accessibilityLayer
          >
            <CartesianGrid
              stroke="var(--color-line)"
              vertical={horizontal}
              horizontal={!horizontal}
            />
            {horizontal ? (
              <>
                <XAxis
                  type="number"
                  tick={tick}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v: number) => formatValue(v, valueFormat, { compact: true })}
                />
                <YAxis
                  type="category"
                  dataKey={x}
                  tick={{
                    ...tick,
                    fontFamily: "var(--font-sans)",
                    fontSize: 12,
                    fill: "var(--color-ink)",
                  }}
                  tickLine={false}
                  axisLine={{ stroke: "var(--color-line-strong)" }}
                  width={150}
                />
              </>
            ) : (
              <>
                <XAxis
                  dataKey={x}
                  tick={tick}
                  tickLine={false}
                  axisLine={{ stroke: "var(--color-line-strong)" }}
                  tickMargin={8}
                />
                <YAxis
                  tick={tick}
                  tickLine={false}
                  axisLine={false}
                  width={64}
                  tickFormatter={(v: number) => formatValue(v, valueFormat, { compact: true })}
                />
              </>
            )}
            <Tooltip
              cursor={{ fill: "var(--color-sage-50)" }}
              content={(props) => (
                <ChartTooltip {...props} valueFormat={valueFormat} xFormat="text" />
              )}
            />
            {series.map((s, i) => (
              <Bar
                key={s.key}
                dataKey={s.key}
                name={s.label}
                fill={s.color ?? SERIES_COLORS[i]}
                fillOpacity={s.muted ? 0.45 : 1}
                radius={horizontal ? [0, 2, 2, 0] : [2, 2, 0, 0]}
                maxBarSize={horizontal ? 18 : 40}
                isAnimationActive={false}
              >
                {single && highlightIndex !== undefined
                  ? data.map((_, index) => (
                      <Cell
                        key={index}
                        fill={
                          index === highlightIndex
                            ? "var(--color-series-1)"
                            : "var(--color-sage-600)"
                        }
                      />
                    ))
                  : null}
              </Bar>
            ))}
            {series.length > 1 ? <Legend content={() => null} /> : null}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </figure>
  );
}

/** Tiny inline trend line for KPI tiles (decorative; the value is the content). */
export function Sparkline({
  values,
  tone = "forest",
}: {
  values: number[];
  tone?: "forest" | "amber" | "ink";
}) {
  if (values.length < 2) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const w = 96;
  const h = 28;
  const points = values
    .map(
      (v, i) =>
        `${((i / (values.length - 1)) * w).toFixed(1)},${(h - ((v - min) / range) * (h - 4) - 2).toFixed(1)}`,
    )
    .join(" ");
  const stroke = {
    forest: "var(--color-forest)",
    amber: "var(--color-amber)",
    ink: "var(--color-ink-3)",
  }[tone];
  return (
    <svg aria-hidden viewBox={`0 0 ${w} ${h}`} className="h-7 w-24 overflow-visible">
      <polyline
        points={points}
        fill="none"
        stroke={stroke}
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}
