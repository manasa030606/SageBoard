import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { Badge, type Tone } from "@/components/ui/badge";
import { InlineBar, Table, TD, TH, THead, TR } from "@/components/ui/table";
import { cn } from "@/lib/cn";
import { formatCurrency, formatInteger, formatPercent, formatRelative } from "@/lib/format";
import type {
  HistoryEntry,
  ProductPerformance,
  RegionPerformance,
  RunStatus,
} from "@/types/domain";

function GrowthText({ value }: { value: number }) {
  return (
    <span
      className={cn("font-mono text-[12.5px] tabular", value >= 0 ? "text-forest" : "text-rust")}
    >
      {formatPercent(value, { signed: true })}
    </span>
  );
}

export function RegionList({ regions }: { regions: RegionPerformance[] }) {
  const max = Math.max(...regions.map((r) => r.revenue));
  const total = regions.reduce((acc, r) => acc + r.revenue, 0);
  return (
    <ul className="divide-y divide-line/70">
      {regions.map((r) => (
        <li
          key={r.region}
          className="grid grid-cols-[1fr_auto] items-center gap-x-4 gap-y-1.5 px-5 py-3"
        >
          <span className="text-[13px] font-medium text-ink">{r.region}</span>
          <span className="text-right font-mono text-[12.5px] text-ink tabular">
            {formatCurrency(r.revenue, { compact: true })}
          </span>
          <InlineBar value={r.revenue} max={max} />
          <span className="flex items-center justify-end gap-2 text-xs text-ink-2">
            <span className="tabular">{formatPercent(r.revenue / total, { digits: 0 })}</span>
            <GrowthText value={r.growth} />
          </span>
        </li>
      ))}
    </ul>
  );
}

export function TopProductsTable({ products }: { products: ProductPerformance[] }) {
  return (
    <Table>
      <caption className="sr-only">Top products by revenue, January to October 2026</caption>
      <THead>
        <tr>
          <TH>Product</TH>
          <TH className="hidden sm:table-cell">Category</TH>
          <TH align="right">Units</TH>
          <TH align="right">Revenue</TH>
          <TH align="right">vs 2025</TH>
        </tr>
      </THead>
      <tbody>
        {products.map((p) => (
          <TR key={p.sku}>
            <TD>
              <p className="font-medium">{p.name}</p>
              <p className="font-mono text-2xs text-ink-2">{p.sku}</p>
            </TD>
            <TD className="hidden text-ink-2 sm:table-cell">{p.category}</TD>
            <TD numeric>{formatInteger(p.unitsSold)}</TD>
            <TD numeric>{formatCurrency(p.revenue)}</TD>
            <TD align="right">
              <GrowthText value={p.growth} />
            </TD>
          </TR>
        ))}
      </tbody>
    </Table>
  );
}

export const RUN_STATUS: Record<RunStatus, { label: string; tone: Tone }> = {
  queued: { label: "Queued", tone: "neutral" },
  running: { label: "Running", tone: "info" },
  awaiting_input: { label: "Needs input", tone: "warning" },
  succeeded: { label: "Answered", tone: "positive" },
  partial: { label: "Partial", tone: "warning" },
  failed: { label: "Failed", tone: "critical" },
  cancelled: { label: "Cancelled", tone: "neutral" },
};

export function RecentAnalyses({ entries, now }: { entries: readonly HistoryEntry[]; now: Date }) {
  return (
    <ul className="divide-y divide-line/70">
      {entries.map((e) => (
        <li key={e.id}>
          <Link
            href={e.scenarioId ? `/app/analyst?sample=${e.scenarioId}` : "/app/history"}
            className="group grid gap-1.5 px-5 py-3 transition-colors duration-100 hover:bg-sage-50 focus-visible:bg-sage-50"
          >
            <span className="line-clamp-2 text-[13px] leading-5 text-ink group-hover:text-forest">
              {e.question}
            </span>
            <span className="flex items-center gap-2 text-2xs text-ink-2">
              <Badge tone={RUN_STATUS[e.status].tone} dot>
                {RUN_STATUS[e.status].label}
              </Badge>
              <span>{formatRelative(e.createdAt, now)}</span>
              {e.insightCount > 0 ? <span>· {e.insightCount} insights</span> : null}
              <ArrowRight
                className="ml-auto size-3.5 opacity-0 transition-opacity group-hover:opacity-100"
                aria-hidden
              />
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
