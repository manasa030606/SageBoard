"use client";

import {
  BarChart3,
  BookmarkPlus,
  ChevronRight,
  CircleSlash,
  Database,
  FileText,
  Loader2,
  Pin,
  Table2,
} from "lucide-react";
import { useState } from "react";

import { ChartRenderer } from "@/components/charts/chart-renderer";
import { ResultTableView } from "@/components/data/result-table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Notice, Skeleton } from "@/components/ui/states";
import { Tabs } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/cn";
import { formatDuration } from "@/lib/format";
import type { SampleScenario } from "@/types/domain";

import { InsightList } from "./insights";
import { SqlViewer } from "./sql-viewer";
import { currentActivity, ExecutionTimeline } from "./timeline";
import { revealedOutputs, type ThreadRun } from "./workspace-state";

type ResultTab = "chart" | "table" | "sql";

export function RunView({
  run,
  scenario,
  datasetName,
  samples,
  followUps,
  onCancel,
  onAsk,
}: {
  run: ThreadRun;
  scenario: SampleScenario | undefined;
  datasetName: string;
  /** Sample questions offered when a question has no recording. */
  samples: SampleScenario[];
  followUps: SampleScenario[];
  onCancel: () => void;
  onAsk: (question: string) => void;
}) {
  return (
    <article aria-labelledby={`${run.id}-q`} className="grid gap-6">
      <header className="grid gap-2.5">
        <div className="flex flex-wrap items-center gap-2 text-xs text-ink-2">
          <span className="inline-flex items-center gap-1.5">
            <Database className="size-3.5" aria-hidden /> {datasetName}
          </span>
          {scenario ? <Badge tone="warning">Sample run</Badge> : null}
          <RunStatusBadge run={run} scenario={scenario} />
        </div>
        <h2 id={`${run.id}-q`} className="text-title text-[22px] text-ink sm:text-[24px]">
          {run.question}
        </h2>
      </header>

      {run.status === "unmatched" || !scenario ? (
        <UnmatchedNotice samples={samples} onAsk={onAsk} />
      ) : (
        <ScenarioBody
          run={run}
          scenario={scenario}
          followUps={followUps}
          onCancel={onCancel}
          onAsk={onAsk}
        />
      )}
    </article>
  );
}

function RunStatusBadge({
  run,
  scenario,
}: {
  run: ThreadRun;
  scenario: SampleScenario | undefined;
}) {
  if (run.status === "running")
    return (
      <Badge tone="info" dot>
        Running
      </Badge>
    );
  if (run.status === "cancelled") return <Badge tone="neutral">Cancelled</Badge>;
  if (run.status === "unmatched") return <Badge tone="neutral">Not run</Badge>;
  if (scenario?.outcome === "partial")
    return (
      <Badge tone="warning" dot>
        Couldn’t answer
      </Badge>
    );
  const duration = scenario?.result.timeline.reduce((acc, t) => acc + t.durationMs, 0) ?? 0;
  return (
    <>
      <Badge tone="positive" dot>
        Answered
      </Badge>
      <span className="tabular">{formatDuration(duration)}</span>
    </>
  );
}

function UnmatchedNotice({
  samples,
  onAsk,
}: {
  samples: SampleScenario[];
  onAsk: (q: string) => void;
}) {
  return (
    <div className="grid gap-4">
      <Notice tone="info" title="This page isn’t connected to the live agent yet">
        This preview runs on recorded sample runs, so it won’t invent an answer to a new question.
        The analysis agent now runs on the server; connecting this workspace to it comes in a later
        phase.
      </Notice>
      {samples.length > 0 ? (
        <div>
          <p className="mb-2 text-[13px] font-medium text-ink">Try a recorded question</p>
          <ul className="grid gap-1.5">
            {samples.map((s) => (
              <li key={s.id}>
                <button
                  type="button"
                  onClick={() => onAsk(s.question)}
                  className="group flex w-full items-center justify-between gap-3 rounded-sm border border-line bg-paper px-3.5 py-2.5 text-left text-sm text-ink transition-colors hover:border-forest/50 hover:bg-sage-50"
                >
                  {s.question}
                  <ChevronRight
                    className="size-4 shrink-0 text-ink-3 group-hover:text-forest"
                    aria-hidden
                  />
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="text-sm text-ink-2">
          There are no recorded sample runs for this dataset. Switch to “Retail demo” to try one.
        </p>
      )}
    </div>
  );
}

function ScenarioBody({
  run,
  scenario,
  followUps,
  onCancel,
  onAsk,
}: {
  run: ThreadRun;
  scenario: SampleScenario;
  followUps: SampleScenario[];
  onCancel: () => void;
  onAsk: (q: string) => void;
}) {
  const { result } = scenario;
  const out = revealedOutputs(result.timeline, run.revealed);
  const live = run.status === "running";
  const [tab, setTab] = useState<ResultTab>("chart");
  const [highlight, setHighlight] = useState<{ rows: number[]; id: string } | null>(null);
  const { notify } = useToast();
  const effectiveTab: ResultTab =
    tab === "chart" && (!out.charted || !result.chart) ? "table" : tab;

  return (
    <>
      {live ? (
        <div
          className="flex items-center justify-between gap-3 rounded-sm border border-line bg-paper px-3.5 py-2.5"
          role="status"
          aria-live="polite"
        >
          <span className="flex items-center gap-2 text-sm text-ink">
            <Loader2 className="size-4 animate-spin text-forest" aria-hidden />
            {currentActivity(result.timeline, run.revealed)}
            <span className="text-xs text-ink-2 tabular">
              step {Math.min(run.revealed + 1, result.timeline.length)} of {result.timeline.length}
            </span>
          </span>
          <Button
            size="sm"
            variant="ghost"
            onClick={onCancel}
            leadingIcon={<CircleSlash className="size-3.5" aria-hidden />}
          >
            Cancel
          </Button>
        </div>
      ) : null}

      {run.status === "cancelled" ? (
        <Notice tone="warning" title="Run cancelled">
          Stopped after {run.revealed} of {result.timeline.length} steps. Nothing was saved. Ask
          again to start over.
        </Notice>
      ) : null}

      {out.understood ? (
        <section aria-label="Interpretation" className="grid animate-rise gap-4 sm:grid-cols-2">
          <div>
            <p className="mb-1.5 eyebrow">Interpreted as</p>
            <p className="text-sm leading-6 text-ink">{result.restatedQuestion}</p>
          </div>
          {result.assumptions.length > 0 ? (
            <div>
              <p className="mb-1.5 eyebrow">Assumptions</p>
              <ul className="grid gap-1 text-[13px] leading-5 text-ink-2">
                {result.assumptions.map((a) => (
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

      {out.planned && result.plan.length > 0 ? (
        <section aria-label="Analysis plan" className="animate-rise">
          <p className="mb-1.5 eyebrow">Plan</p>
          <ol className="grid gap-1.5">
            {result.plan.map((p, i) => (
              <li key={p.id} className="flex gap-3 text-sm leading-6 text-ink">
                <span className="font-mono text-xs leading-6 text-ink-3 tabular">{i + 1}.</span>
                {p.purpose}
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      {/* Inline trace for screens without the side inspector */}
      <details className="group rounded-sm border border-line bg-paper xl:hidden" open={live}>
        <summary className="flex cursor-pointer list-none items-center justify-between px-3.5 py-2.5 text-[13px] font-medium text-ink">
          Execution trace
          <span className="text-xs font-normal text-ink-2">
            {Math.min(run.revealed, result.timeline.length)} / {result.timeline.length} steps
            <ChevronRight
              className="ml-1 inline size-3.5 transition-transform group-open:rotate-90"
              aria-hidden
            />
          </span>
        </summary>
        <div className="border-t border-line px-3.5 py-3.5">
          <ExecutionTimeline
            steps={result.timeline}
            revealed={run.revealed}
            live={live}
            cancelled={run.status === "cancelled"}
            compact
          />
        </div>
      </details>

      {result.table ? (
        out.executed ? (
          <section
            aria-label="Result"
            className="animate-rise overflow-hidden rounded-md border border-line bg-paper"
          >
            <Tabs<ResultTab>
              label="Result views"
              value={effectiveTab}
              onChange={setTab}
              className="[&_[role=tablist]]:px-3"
              items={[
                ...(result.chart && out.charted
                  ? [
                      {
                        key: "chart" as const,
                        label: (
                          <>
                            <BarChart3 className="size-3.5" aria-hidden /> Chart
                          </>
                        ),
                      },
                    ]
                  : []),
                {
                  key: "table",
                  label: (
                    <>
                      <Table2 className="size-3.5" aria-hidden /> Table
                    </>
                  ),
                  count: result.table.rowCount,
                },
                { key: "sql", label: "SQL", count: result.sqlAttempts.length },
              ]}
              renderPanel={(key) =>
                key === "chart" && result.chart && result.table ? (
                  <div className="px-3 pt-4 pb-3">
                    <div className="mb-2 px-2">
                      <p className="text-sm font-semibold text-ink">{result.chart.title}</p>
                      {result.chart.subtitle ? (
                        <p className="text-xs text-ink-2">{result.chart.subtitle}</p>
                      ) : null}
                    </div>
                    <ChartRenderer spec={result.chart} table={result.table} />
                  </div>
                ) : key === "table" && result.table ? (
                  <ResultTableView
                    table={result.table}
                    highlightRows={highlight?.rows}
                    fileName={scenario.id}
                  />
                ) : (
                  <SqlViewer attempts={result.sqlAttempts} />
                )
              }
            />
          </section>
        ) : (
          <div className="flex items-center gap-4 rounded-md border border-dashed border-line-strong px-5 py-6">
            <div aria-hidden className="grid flex-1 gap-2">
              <Skeleton className="h-3 w-32" />
              <Skeleton className="h-3 w-full max-w-md" />
              <Skeleton className="h-3 w-full max-w-sm" />
            </div>
            <p className="text-[13px] text-ink-2">
              {live
                ? "Results appear once the query runs."
                : "No results: the run stopped before the query ran."}
            </p>
          </div>
        )
      ) : null}

      {result.insights.length > 0 ? (
        out.verified ? (
          <section aria-labelledby={`${run.id}-insights`} className="animate-rise">
            <div className="mb-3 flex items-baseline justify-between gap-3">
              <h3 id={`${run.id}-insights`} className="text-[15px] font-semibold text-ink">
                What the data shows
              </h3>
              <span className="text-xs text-ink-2">
                Every insight cites the rows or facts it uses
              </span>
            </div>
            <InsightList
              insights={result.insights}
              activeEvidence={highlight?.id ?? null}
              onEvidence={(rows, id) => {
                setHighlight({ rows, id });
                setTab("table");
              }}
            />
          </section>
        ) : out.executed ? (
          <div className="grid gap-2.5" aria-hidden>
            <Skeleton className="h-3.5 w-48" />
            <Skeleton className="h-4 w-full max-w-xl" />
            <Skeleton className="h-4 w-full max-w-lg" />
          </div>
        ) : null
      ) : null}

      {out.complete && scenario.outcome === "partial" ? (
        <div className="grid gap-4">
          <Notice tone="warning" title="This dataset can’t answer that question">
            {scenario.failureReason}
          </Notice>
          <ul className="grid gap-1 text-[13px] text-ink-2">
            {result.limitations.map((l) => (
              <li key={l} className="flex gap-2">
                <span aria-hidden className="mt-2 size-1 shrink-0 rounded-full bg-ink-3" />
                {l}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {out.complete && scenario.outcome !== "partial" && result.limitations.length > 0 ? (
        <section aria-label="Limitations" className="border-t border-line pt-4">
          <p className="mb-1.5 eyebrow">Limitations</p>
          <ul className="grid gap-1 text-[13px] leading-5 text-ink-2">
            {result.limitations.map((l) => (
              <li key={l}>{l}</li>
            ))}
          </ul>
        </section>
      ) : null}

      {out.complete && run.status === "done" ? (
        <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4">
          <div className="flex flex-wrap gap-2">
            {result.table ? (
              <>
                <Button
                  size="sm"
                  variant="secondary"
                  leadingIcon={<FileText className="size-3.5" aria-hidden />}
                  onClick={() =>
                    notify({
                      tone: "success",
                      title: "Saved as report",
                      description: "Find it under Reports (demo: not persisted).",
                    })
                  }
                >
                  Save as report
                </Button>
                {result.chart ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    leadingIcon={<Pin className="size-3.5" aria-hidden />}
                    onClick={() =>
                      notify({
                        tone: "success",
                        title: "Chart pinned to dashboard",
                        description: "Demo: not persisted yet.",
                      })
                    }
                  >
                    Pin chart
                  </Button>
                ) : null}
              </>
            ) : null}
          </div>
          <span className="text-xs text-ink-2 tabular">
            {result.usage.llmCalls} model calls · {result.usage.sqlExecutions}{" "}
            {result.usage.sqlExecutions === 1 ? "query" : "queries"} ·{" "}
            {result.usage.tokens.toLocaleString("en-US")} tokens
          </span>
        </footer>
      ) : null}

      {out.complete && run.status === "done" && followUps.length > 0 ? (
        <section aria-label="Suggested follow-ups">
          <p className="mb-2 flex items-center gap-1.5 text-[13px] font-medium text-ink">
            <BookmarkPlus className="size-3.5 text-forest" aria-hidden /> Ask next
          </p>
          <div className="flex flex-wrap gap-2">
            {followUps.map((f) => (
              <button
                key={f.id}
                type="button"
                onClick={() => onAsk(f.question)}
                className={cn(
                  "rounded-sm border border-line bg-paper px-3 py-1.5 text-left text-[13px] text-ink transition-colors",
                  "hover:border-forest/50 hover:bg-sage-50",
                )}
              >
                {f.question}
              </button>
            ))}
          </div>
        </section>
      ) : null}
    </>
  );
}
