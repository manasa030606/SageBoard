import { ArrowDownRight, ArrowUpRight } from "lucide-react";

import { Sparkline } from "@/components/charts/charts";
import { cn } from "@/lib/cn";
import { formatPercent, formatValue } from "@/lib/format";
import type { Kpi } from "@/types/domain";

function Delta({ value }: { value: number }) {
  const up = value >= 0;
  const Icon = up ? ArrowUpRight : ArrowDownRight;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-0.5 text-[13px] font-medium tabular",
        up ? "text-forest" : "text-rust",
      )}
    >
      <Icon className="size-3.5" aria-hidden />
      <span className="sr-only">{up ? "Up" : "Down"} </span>
      {formatPercent(Math.abs(value))}
    </span>
  );
}

/** One bordered strip divided by hairlines — four metrics without four cards. */
export function KpiStrip({ kpis }: { kpis: Kpi[] }) {
  return (
    <dl className="grid grid-cols-1 overflow-hidden rounded-md border border-line bg-paper sm:grid-cols-2 xl:grid-cols-4">
      {kpis.map((kpi, i) => (
        <div
          key={kpi.key}
          className={cn(
            "flex flex-col gap-3 px-5 py-5",
            i > 0 && "border-t border-line sm:border-t-0",
            i % 2 === 1 && "sm:border-l",
            i >= 2 && "sm:border-t xl:border-t-0",
            i > 0 && "xl:border-l",
          )}
        >
          <dt className="text-[13px] text-ink-2">{kpi.label}</dt>
          <dd className="flex items-end justify-between gap-3">
            <div>
              <p className="text-[28px] leading-none font-medium tracking-tight text-ink tabular">
                {kpi.format === "percent"
                  ? formatPercent(kpi.value, { signed: true })
                  : formatValue(kpi.value, kpi.format, { compact: kpi.format === "currency" })}
              </p>
              <p className="mt-2 flex flex-wrap items-center gap-x-1.5 text-xs text-ink-2">
                {kpi.delta !== null ? <Delta value={kpi.delta} /> : null}
                <span>{kpi.comparisonLabel}</span>
              </p>
            </div>
            <Sparkline values={kpi.sparkline} tone={kpi.key === "growth" ? "amber" : "forest"} />
          </dd>
        </div>
      ))}
    </dl>
  );
}
