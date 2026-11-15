"use client";

import {
  BookmarkPlus,
  ChevronRight,
  CircleSlash,
  Database,
  FileText,
  Loader2,
  Table2,
} from "lucide-react";
import { useState } from "react";

import { ChartRenderer } from "@/components/charts/chart-renderer";
import { ResultTableView } from "@/components/data/result-table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Notice, Skeleton } from "@/components/ui/states";
import { useToast } from "@/components/ui/toast";
import { analysis, reports } from "@/lib/api/endpoints";
import type { SessionDetail } from "@/lib/api/types";
import { toApiError } from "@/lib/use-api";
import { cn } from "@/lib/cn";
import { formatDuration } from "@/lib/format";

import { InsightList } from "../insights";
import { SqlCode, SqlViewer } from "../sql-viewer";
import { ExecutionTimeline } from "../timeline";
import { adaptRun, adaptTimeline, liveActivity, type LiveRun, type LiveStep } from "./adapt";
import { useLiveSession } from "./use-live-session";

export function RunCard({
  sessionId,
  question,
  datasetName,
  onAsk,
  onSettled,
  defaultOpen,
}: {
  sessionId: string;
  question: string;
  datasetName: string;
  /** Ask a follow-up or answer a clarification (posts in the same conversation). */
  onAsk: (question: string) => void;
  onSettled?: (detail: SessionDetail) => void;
  /** Older runs start collapsed; the latest starts open. */
  defaultOpen: boolean;
}) {
  const { detail, trace, error } = useLiveSession(sessionId, onSettled);
  const [open, setOpen] = useState(defaultOpen);
  const live = detail === undefined || detail.status === "queued" || detail.status === "running";
  const run = detail ? adaptRun(detail) : null;

  return (
    <article aria-labelledby={`${sessionId}-q`} className="grid gap-5">
      <header className="grid gap-2">
        <div className="flex flex-wrap items-center gap-2 text-xs text-ink-2">
          <span className="inline-flex items-center gap-1.5">
            <Database className="size-3.5" aria-hidden /> {datasetName}
          </span>
          <StatusBadge run={run} loading={detail === undefined} />
          {run?.durationMs ? <span className="tabular">{formatDuration(run.durationMs)}</span> : null}
        </div>
        <h2 id={`${sessionId}-q`} className="text-title text-[22px] text-ink sm:text-[24px]">
          {detail?.question ?? question}
        </h2>
      </header>

      {error && detail === undefined ? (
        <Notice tone="error" title="Couldn’t load this analysis">
          {error.message} Retrying…
        </Notice>
      ) : null}

      {live ? (
        <LiveProgress
          activity={detail === undefined ? "Loading…" : liveActivity(trace)}
          trace={trace}
          onCancel={detail ? () => void analysis.cancel(sessionId).catch(() => undefined) : null}
        />
      ) : null}

      {run && !live ? (
        open ? (
          <RunBody run={run} sessionId={sessionId} onAsk={onAsk} />
        ) : (
          <button
            type="button"
            onClick={() => setOpen(true)}
            className="group flex items-center justify-between gap-3 rounded-sm border border-line bg-paper px-3.5 py-2.5 text-left text-sm text-ink-2 transition-colors hover:border-forest/50 hover:bg-sage-50"
          >
            <span className="line-clamp-2">{run.summary ?? "Show this analysis"}</span>
            <ChevronRight className="size-4 shrink-0 text-ink-3 group-hover:text-forest" aria-hidden />
          </button>
        )
      ) : null}
    </article>
  );
}

function StatusBadge({ run, loading }: { run: LiveRun | null; loading: boolean }) {
  if (loading) return <Badge tone="neutral">Loading</Badge>;
  switch (run?.status) {
    case "queued":
      return <Badge tone="neutral" dot>Queued</Badge>;
    case "running":
      return <Badge tone="info" dot>Running</Badge>;
    case "awaiting_input":
      return <Badge tone="warning" dot>Needs an answer</Badge>;
    case "succeeded":
      return run.responseStatus === "out_of_scope" ? (
        <Badge tone="neutral">Can’t answer</Badge>
      ) : (
        <Badge tone="positive" dot>Answered</Badge>
      );
    case "partial":
      return <Badge tone="warning" dot>Partial answer</Badge>;
    case "cancelled":
      return <Badge tone="neutral">Cancelled</Badge>;
    default:
      return <Badge tone="critical">Failed</Badge>;
  }
}

function LiveProgress({
  activity,
  trace,
  onCancel,
}: {
  activity: string;
  trace: Parameters<typeof adaptTimeline>[0];
  onCancel: (() => void) | null;
}) {
  const steps = adaptTimeline(trace);
  return (
    <div className="grid gap-3">
      <div
        className="flex items-center justify-between gap-3 rounded-sm border border-line bg-paper px-3.5 py-2.5"
        role="status"
        aria-live="polite"
      >
        <span className="flex items-center gap-2 text-sm text-ink">
          <Loader2 className="size-4 animate-spin text-forest" aria-hidden />
          {activity}
          <span className="text-xs text-ink-2 tabular">{steps.length} steps done</span>
        </span>
        {onCancel ? (
          <Button
            size="sm"
            variant="ghost"
            onClick={onCancel}
            leadingIcon={<CircleSlash className="size-3.5" aria-hidden />}
          >
            Cancel
          </Button>
        ) : null}
      </div>
      {steps.length > 0 ? (
        <details className="group rounded-sm border border-line bg-paper">
          <summary className="flex cursor-pointer list-none items-center justify-between px-3.5 py-2.5 text-[13px] font-medium text-ink">
            Execution trace
            <ChevronRight className="size-3.5 transition-transform group-open:rotate-90" aria-hidden />
          </summary>
          <div className="border-t border-line px-3.5 py-3.5">
            <ExecutionTimeline steps={steps} revealed={steps.length} live={false} compact />
          </div>
        </details>
      ) : (
        <div aria-hidden className="grid gap-2 rounded-md border border-dashed border-line-strong px-5 py-5">
          <Skeleton className="h-3 w-40" />
          <Skeleton className="h-3 w-full max-w-md" />
        </div>
      )}
    </div>
  );
}

const ANSWER_TONE: Record<string, "success" | "warning" | "info" | "error"> = {
  answered: "success",
  partial: "warning",
  out_of_scope: "info",
  clarification_needed: "info",
  failed: "error",
};

function RunBody({
  run,
  sessionId,
  onAsk,
}: {
  run: LiveRun;
  sessionId: string;
  onAsk: (question: string) => void;
}) {
  const [highlight, setHighlight] = useState<{ stepId: string; rows: number[]; id: string } | null>(
    null,
  );
  const [openStep, setOpenStep] = useState<string | null>(null);
  const { notify } = useToast();
  const answered = run.status === "succeeded" || run.status === "partial";

  async function saveReport() {
    try {
      const report = await reports.create(sessionId);
      notify({
        tone: "success",
        title: "Saved as report",
        description: `“${report.title}” is now under Reports.`,
      });
    } catch (err) {
      notify({ tone: "error", title: "Couldn’t save the report", description: toApiError(err).message });
    }
  }

  return (
    <>
      {run.clarification ? (
        <Notice tone="info" title={run.clarification.question}>
          <div className="mt-2 flex flex-wrap gap-2">
            {run.clarification.options.map((option) => (
              <Button key={option} size="sm" variant="secondary" onClick={() => onAsk(option)}>
                {option}
              </Button>
            ))}
          </div>
          <p className="mt-2 text-xs text-ink-2">…or type your own answer below.</p>
        </Notice>
      ) : null}

      {run.failureReason ? (
        <Notice
          tone={run.status === "cancelled" ? "warning" : "error"}
          title={run.status === "cancelled" ? "Analysis cancelled" : "The analysis failed"}
        >
          {run.failureReason}
        </Notice>
      ) : null}

      {run.summary && answered ? (
        <Notice tone={ANSWER_TONE[run.responseStatus ?? "answered"] ?? "info"} title="Answer">
          {run.summary}
        </Notice>
      ) : null}

      {run.restated || run.assumptions.length > 0 ? (
        <section aria-label="Interpretation" className="grid gap-4 sm:grid-cols-2">
          {run.restated ? (
            <div>
              <p className="mb-1.5 eyebrow">Interpreted as</p>
              <p className="text-sm leading-6 text-ink">{run.restated}</p>
            </div>
          ) : null}
          {run.assumptions.length > 0 ? (
            <div>
              <p className="mb-1.5 eyebrow">Assumptions</p>
              <ul className="grid gap-1 text-[13px] leading-5 text-ink-2">
                {run.assumptions.map((a) => (
                  <li key={a} className="flex gap-2">
                    <span aria-hidden className="mt-2 size-1 shrink-0 rounded-full bg-ink-3" />
                    {a}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </section>
      ) : null}

      {run.charts.map((chart) =>
        chart.table ? (
          <section
            key={`${chart.spec.title}-${chart.spec.chartType}`}
            aria-label={chart.spec.title}
            className="overflow-hidden rounded-md border border-line bg-paper"
          >
            <div className="px-5 pt-4">
              <p className="text-sm font-semibold text-ink">{chart.spec.title}</p>
              {chart.spec.subtitle ? <p className="text-xs text-ink-2">{chart.spec.subtitle}</p> : null}
              {chart.fallbackReason ? (
                <p className="mt-1 text-xs text-ink-3">Shown as a table: {chart.fallbackReason}</p>
              ) : null}
            </div>
            <div className="px-3 pt-3 pb-3">
              {chart.spec.chartType === "table" ? (
                <ResultTableView table={chart.table} maxHeight={320} />
              ) : (
                (ChartRenderer({ spec: chart.spec, table: chart.table }) ?? (
                  <ResultTableView table={chart.table} maxHeight={320} />
                ))
              )}
            </div>
          </section>
        ) : null,
      )}

      {run.insights.length > 0 ? (
        <section aria-label="What the data shows">
          <div className="mb-3 flex items-baseline justify-between gap-3">
            <h3 className="text-[15px] font-semibold text-ink">What the data shows</h3>
            <span className="text-xs text-ink-2">Every insight cites the rows or facts it uses</span>
          </div>
          <InsightList
            insights={run.insights}
            activeEvidence={highlight?.id ?? null}
            onEvidence={(rows, id, stepId) => {
              const target = stepId ?? run.steps[0]?.id;
              if (!target) return;
              setHighlight({ stepId: target, rows, id });
              setOpenStep(target);
              document.getElementById(`${sessionId}-${target}`)?.scrollIntoView({ block: "nearest" });
            }}
          />
        </section>
      ) : null}

      {run.steps.length > 0 ? (
        <section aria-label="Queries and results" className="grid gap-2">
          <p className="eyebrow">Queries & results</p>
          {run.steps.map((step, i) => (
            <StepDetails
              key={step.id}
              step={step}
              index={i}
              anchorId={`${sessionId}-${step.id}`}
              open={openStep === step.id || (run.steps.length === 1 && openStep === null)}
              onToggle={(next) => setOpenStep(next ? step.id : null)}
              highlightRows={highlight?.stepId === step.id ? highlight.rows : []}
            />
          ))}
        </section>
      ) : null}

      {run.caveats.length > 0 ? (
        <section aria-label="Limitations" className="border-t border-line pt-4">
          <p className="mb-1.5 eyebrow">Limitations</p>
          <ul className="grid gap-1 text-[13px] leading-5 text-ink-2">
            {run.caveats.map((caveat) => (
              <li key={caveat} className="flex gap-2">
                <span aria-hidden className="mt-2 size-1 shrink-0 rounded-full bg-ink-3" />
                {caveat}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {answered ? (
        <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4">
          <Button
            size="sm"
            variant="secondary"
            leadingIcon={<FileText className="size-3.5" aria-hidden />}
            onClick={() => void saveReport()}
          >
            Save as report
          </Button>
          {run.usage ? (
            <span className="text-xs text-ink-2 tabular">
              {run.usage.llmCalls} model calls · {run.usage.sqlExecutions}{" "}
              {run.usage.sqlExecutions === 1 ? "query" : "queries"} ·{" "}
              {run.usage.tokens.toLocaleString("en-US")} tokens
              {run.model ? ` · ${run.model}` : ""}
            </span>
          ) : null}
        </footer>
      ) : null}

      {answered && run.followUps.length > 0 ? (
        <section aria-label="Suggested follow-ups">
          <p className="mb-2 flex items-center gap-1.5 text-[13px] font-medium text-ink">
            <BookmarkPlus className="size-3.5 text-forest" aria-hidden /> Ask next
          </p>
          <div className="flex flex-wrap gap-2">
            {run.followUps.map((followUp) => (
              <button
                key={followUp}
                type="button"
                onClick={() => onAsk(followUp)}
                className={cn(
                  "rounded-sm border border-line bg-paper px-3 py-1.5 text-left text-[13px] text-ink transition-colors",
                  "hover:border-forest/50 hover:bg-sage-50",
                )}
              >
                {followUp}
              </button>
            ))}
          </div>
        </section>
      ) : null}
    </>
  );
}

const STEP_BADGE: Record<LiveStep["status"], { tone: "positive" | "warning" | "neutral" | "critical"; label: string }> = {
  succeeded: { tone: "positive", label: "Succeeded" },
  failed: { tone: "critical", label: "Failed" },
  skipped: { tone: "neutral", label: "Skipped" },
  pending: { tone: "neutral", label: "Not run" },
};

function StepDetails({
  step,
  index,
  anchorId,
  open,
  onToggle,
  highlightRows,
}: {
  step: LiveStep;
  index: number;
  anchorId: string;
  open: boolean;
  onToggle: (open: boolean) => void;
  highlightRows: number[];
}) {
  const badge = STEP_BADGE[step.status];
  const [tab, setTab] = useState<"table" | "sql">("table");
  return (
    <details
      id={anchorId}
      className="group overflow-hidden rounded-md border border-line bg-paper"
      open={open}
      onToggle={(event) => onToggle((event.target as HTMLDetailsElement).open)}
    >
      <summary className="flex cursor-pointer list-none items-center gap-3 px-3.5 py-2.5">
        <span className="font-mono text-xs text-ink-3 tabular">{index + 1}.</span>
        <span className="min-w-0 flex-1 truncate text-sm text-ink">{step.purpose}</span>
        <Badge tone={badge.tone}>{badge.label}</Badge>
        {step.table ? (
          <span className="hidden items-center gap-1 text-xs text-ink-2 tabular sm:inline-flex">
            <Table2 className="size-3.5" aria-hidden /> {step.table.rowCount}
            {step.table.truncated ? "+" : ""} rows
          </span>
        ) : null}
        <ChevronRight className="size-4 text-ink-3 transition-transform group-open:rotate-90" aria-hidden />
      </summary>
      <div className="border-t border-line">
        {step.failure ? (
          <p className="px-4 py-3 text-sm leading-6 text-amber-ink">{step.failure}</p>
        ) : null}
        {step.notes.map((note) => (
          <p key={note} className="px-4 pt-3 text-xs text-ink-2">
            {note}
          </p>
        ))}
        {step.table ? (
          <>
            <div className="flex gap-1 px-3 pt-2" role="tablist" aria-label="Step views">
              {(["table", "sql"] as const).map((key) => (
                <button
                  key={key}
                  type="button"
                  role="tab"
                  aria-selected={tab === key}
                  onClick={() => setTab(key)}
                  className={cn(
                    "rounded-xs px-2.5 py-1 text-xs font-medium transition-colors",
                    tab === key ? "bg-sage-100 text-ink" : "text-ink-2 hover:text-ink",
                  )}
                >
                  {key === "table" ? "Table" : `SQL (${step.attempts.length})`}
                </button>
              ))}
            </div>
            {tab === "table" ? (
              <ResultTableView table={step.table} highlightRows={highlightRows} fileName={step.id} />
            ) : step.attempts.length > 1 ? (
              <SqlViewer attempts={step.attempts} />
            ) : step.sql ? (
              <div className="px-4 py-3">
                <SqlCode sql={step.sql} />
              </div>
            ) : null}
          </>
        ) : step.sql || step.attempts.length > 0 ? (
          <div className="px-4 py-3">
            {step.attempts.length > 1 ? (
              <SqlViewer attempts={step.attempts} />
            ) : (
              <SqlCode sql={step.sql ?? step.attempts[0]?.sql ?? ""} />
            )}
          </div>
        ) : null}
      </div>
    </details>
  );
}
