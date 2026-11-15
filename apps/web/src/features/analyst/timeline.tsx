"use client";

import { Check, Circle, Loader2, Minus, RotateCcw, X } from "lucide-react";

import { cn } from "@/lib/cn";
import { formatDuration } from "@/lib/format";
import type { TimelineStep } from "@/types/domain";

type DisplayStatus = TimelineStep["status"] | "running" | "pending" | "cancelled";

const ICONS: Record<DisplayStatus, { icon: typeof Check; className: string; label: string }> = {
  succeeded: { icon: Check, className: "bg-forest text-warm", label: "Completed" },
  recovered: { icon: RotateCcw, className: "bg-forest text-warm", label: "Recovered" },
  failed: { icon: X, className: "bg-amber text-navy", label: "Failed, will retry" },
  skipped: { icon: Minus, className: "bg-warm-300 text-ink-2", label: "Skipped" },
  running: {
    icon: Loader2,
    className: "bg-paper text-forest ring-1 ring-forest",
    label: "In progress",
  },
  pending: {
    icon: Circle,
    className: "bg-paper text-line-strong ring-1 ring-line",
    label: "Pending",
  },
  cancelled: { icon: Minus, className: "bg-warm-300 text-ink-2", label: "Cancelled" },
};

/**
 * Agent execution timeline. `revealed` steps are shown with their recorded outcome;
 * the next one is "running" while the run is live; the rest are pending.
 */
export function ExecutionTimeline({
  steps,
  revealed,
  live,
  cancelled = false,
  compact = false,
}: {
  steps: TimelineStep[];
  revealed: number;
  live: boolean;
  cancelled?: boolean;
  compact?: boolean;
}) {
  return (
    <ol className="relative grid" aria-label="Agent execution steps">
      {steps.map((step, i) => {
        const status: DisplayStatus =
          i < revealed
            ? step.status
            : i === revealed && live
              ? "running"
              : i === revealed && cancelled
                ? "cancelled"
                : "pending";
        const { icon: Icon, className, label } = ICONS[status];
        const visible = i < revealed;
        const last = i === steps.length - 1;
        return (
          <li
            key={step.id}
            className="relative grid grid-cols-[20px_1fr] gap-3 pb-4 last:pb-0"
            aria-current={status === "running" ? "step" : undefined}
          >
            {!last ? (
              <span
                aria-hidden
                className={cn(
                  "absolute top-5 bottom-0 left-[9.5px] w-px",
                  i < revealed - 1 ? "bg-forest/40" : "bg-line",
                )}
              />
            ) : null}
            <span
              className={cn(
                "relative z-[1] mt-0.5 grid size-5 place-items-center rounded-full",
                className,
              )}
            >
              <Icon
                className={cn("size-3", status === "running" && "animate-spin")}
                strokeWidth={2.5}
                aria-hidden
              />
              <span className="sr-only">{label}</span>
            </span>
            <div className={cn("min-w-0", visible && "animate-rise")}>
              <div className="flex items-baseline justify-between gap-3">
                <p
                  className={cn(
                    "text-[13px] font-medium",
                    status === "pending" ? "text-ink-3" : "text-ink",
                  )}
                >
                  {status === "pending" || status === "running" ? pendingLabel(step) : step.label}
                </p>
                {visible && step.durationMs > 0 ? (
                  <span className="shrink-0 font-mono text-2xs text-ink-3 tabular">
                    {formatDuration(step.durationMs)}
                  </span>
                ) : null}
              </div>
              {visible ? (
                <p
                  className={cn(
                    "mt-0.5 text-xs leading-5",
                    step.status === "failed" ? "text-amber-ink" : "text-ink-2",
                  )}
                >
                  {step.detail}
                </p>
              ) : null}
              {visible && step.tools && !compact ? (
                <ul className="mt-1.5 flex flex-wrap gap-1">
                  {step.tools.map((tool) => (
                    <li
                      key={tool}
                      className="rounded-xs border border-line bg-warm/60 px-1.5 py-px font-mono text-[10.5px] text-ink-2"
                    >
                      {tool}
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

const PENDING: Record<TimelineStep["node"], string> = {
  load_context: "Loading the dataset catalog",
  check_result: "Checking the result",
  finish_step: "Closing the step",
  recover_error: "Correcting the query",
  compose_response: "Composing the answer",
  understand_query: "Understanding the question",
  retrieve_schema: "Reading the schema",
  plan_analysis: "Planning the analysis",
  generate_sql: "Writing SQL",
  validate_sql: "Validating SQL",
  execute_sql: "Running the query",
  analyze_results: "Analysing results",
  generate_visualization: "Choosing a chart",
  generate_insights: "Drafting insights",
  verify_insights: "Verifying insights",
  compose_report: "Composing the answer",
};

function pendingLabel(step: TimelineStep): string {
  return PENDING[step.node];
}

export function currentActivity(steps: TimelineStep[], revealed: number): string {
  const next = steps[revealed];
  return next ? `${pendingLabel(next)}…` : "Finishing…";
}
