"use client";

import {
  AlertTriangle,
  ArrowUpRight,
  Lightbulb,
  Scale,
  ShieldAlert,
  TrendingUp,
} from "lucide-react";

import { cn } from "@/lib/cn";
import type { EvidenceRef, Insight } from "@/types/domain";

const CATEGORY: Record<
  Insight["category"],
  { label: string; icon: typeof Lightbulb; accent: string }
> = {
  finding: { label: "Finding", icon: TrendingUp, accent: "text-forest" },
  comparison: { label: "Comparison", icon: Scale, accent: "text-navy" },
  anomaly: { label: "Anomaly", icon: AlertTriangle, accent: "text-amber-ink" },
  recommendation: { label: "Suggestion", icon: Lightbulb, accent: "text-forest" },
  caveat: { label: "Caveat", icon: ShieldAlert, accent: "text-ink-2" },
};

const CONFIDENCE: Record<Insight["confidence"], string> = {
  high: "High confidence",
  medium: "Medium confidence",
  low: "Low confidence",
};

export function InsightList({
  insights,
  onEvidence,
  activeEvidence,
}: {
  insights: Insight[];
  onEvidence?: (rows: number[], evidenceId: string) => void;
  activeEvidence?: string | null;
}) {
  return (
    <ol className="divide-y divide-line">
      {insights.map((insight, index) => {
        const meta = CATEGORY[insight.category];
        const Icon = meta.icon;
        return (
          <li
            key={insight.id}
            className="grid grid-cols-[28px_1fr] gap-3 py-4 first:pt-0 last:pb-0"
          >
            <span className="pt-0.5 font-mono text-xs text-ink-3 tabular">
              {String(index + 1).padStart(2, "0")}
            </span>
            <div className="min-w-0">
              <p
                className={cn(
                  "flex items-center gap-1.5 text-2xs font-medium tracking-[0.06em] uppercase",
                  meta.accent,
                )}
              >
                <Icon className="size-3.5" aria-hidden />
                {meta.label}
                <span className="font-normal tracking-normal text-ink-3 normal-case">
                  · {CONFIDENCE[insight.confidence]}
                </span>
              </p>
              <p className="mt-1.5 text-[15px] leading-6 font-medium text-ink">
                {insight.headline}
              </p>
              <p className="mt-1 text-sm leading-6 text-ink-2">{insight.detail}</p>
              <ul className="mt-2.5 flex flex-wrap gap-1.5" aria-label="Evidence">
                {insight.evidence.map((ev, i) => (
                  <li key={i}>
                    <EvidenceChip
                      evidence={ev}
                      active={activeEvidence === `${insight.id}-${i}`}
                      onSelect={
                        onEvidence && ev.rowIndices?.length
                          ? () => onEvidence(ev.rowIndices ?? [], `${insight.id}-${i}`)
                          : undefined
                      }
                      id={`${insight.id}-${i}`}
                    />
                  </li>
                ))}
              </ul>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function EvidenceChip({
  evidence,
  onSelect,
  active,
  id,
}: {
  evidence: EvidenceRef;
  onSelect?: () => void;
  active: boolean;
  id: string;
}) {
  const content = (
    <>
      <span className="text-ink-3">{evidence.kind === "rows" ? "Rows" : "Fact"}</span>
      <span className="text-ink">{evidence.label}</span>
      {evidence.value ? (
        <span className="font-mono text-ink tabular">· {evidence.value}</span>
      ) : null}
    </>
  );
  const cls =
    "inline-flex items-center gap-1.5 rounded-xs border px-2 py-0.5 text-xs transition-colors duration-150";
  if (!onSelect) return <span className={cn(cls, "border-line bg-warm/60")}>{content}</span>;
  return (
    <button
      type="button"
      onClick={onSelect}
      data-evidence={id}
      aria-label={`Show evidence: ${evidence.label} in the result table`}
      className={cn(
        cls,
        active
          ? "border-amber bg-amber-100"
          : "border-line bg-paper hover:border-amber hover:bg-amber-100/60",
      )}
    >
      {content}
      <ArrowUpRight className="size-3 text-ink-3" aria-hidden />
    </button>
  );
}
