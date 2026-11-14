"use client";

import { Activity, Database, MessagesSquare, Plus } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useReducer, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Drawer } from "@/components/ui/drawer";
import { Select } from "@/components/ui/field";
import { EmptyState } from "@/components/ui/states";
import { cn } from "@/lib/cn";
import { formatDuration } from "@/lib/format";
import type { Conversation, Dataset, SampleScenario } from "@/types/domain";

import { Composer } from "./composer";
import { ConversationList } from "./conversation-list";
import { RunView } from "./run-view";
import { ExecutionTimeline } from "./timeline";
import { initialWorkspace, replayDelay, workspaceReducer, type ThreadRun } from "./workspace-state";

const normalise = (t: string) =>
  t
    .toLowerCase()
    .replace(/[^a-z0-9 ]/g, " ")
    .replace(/\s+/g, " ")
    .trim();

export function AnalystWorkspace({
  datasets,
  scenarios,
  conversations,
  conversationScenario,
  nowIso,
}: {
  datasets: readonly Dataset[];
  scenarios: readonly SampleScenario[];
  conversations: readonly Conversation[];
  /** conversationId → scenario recorded for it (for reopening past analyses). */
  conversationScenario: Record<string, string>;
  nowIso: string;
}) {
  const now = useMemo(() => new Date(nowIso), [nowIso]);
  const ready = datasets.filter((d) => d.status === "ready");
  const [state, dispatch] = useReducer(
    workspaceReducer,
    initialWorkspace(
      ready[0]?.id ?? "",
      conversations.map((c) => ({
        id: c.id,
        title: c.title,
        datasetId: c.datasetId,
        updatedAt: c.updatedAt,
      })),
    ),
  );
  const [listOpen, setListOpen] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(false);
  const threadEnd = useRef<HTMLDivElement>(null);
  const params = useSearchParams();
  const handledSample = useRef(false);

  const scenarioById = useMemo(() => new Map(scenarios.map((s) => [s.id, s])), [scenarios]);
  const datasetScenarios = scenarios.filter((s) => s.datasetId === state.datasetId);
  const datasetName = (id: string) => datasets.find((d) => d.id === id)?.name ?? "Dataset";
  const thread = state.runs.filter((r) => r.conversationId === state.activeConversationId);
  const runningRun = state.runs.find((r) => r.status === "running");
  const focused = state.runs.find((r) => r.id === state.focusedRunId) ?? thread.at(-1);

  function findScenario(question: string): SampleScenario | undefined {
    const wanted = normalise(question);
    return datasetScenarios.find((s) => normalise(s.question) === wanted);
  }

  function ask(question: string) {
    dispatch({ type: "ask", question, scenario: findScenario(question), nowIso });
  }

  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReducedMotion(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  // Deep link from the dashboard/history: /app/analyst?sample=<scenario id>
  useEffect(() => {
    if (handledSample.current) return;
    handledSample.current = true;
    const id = params.get("sample");
    const s = id ? scenarioById.get(id) : undefined;
    if (s) dispatch({ type: "ask", question: s.question, scenario: s, nowIso });
  }, [params, scenarioById, nowIso]);

  // Replay driver: reveal the next recorded step after a delay proportional to its duration.
  useEffect(() => {
    if (!runningRun?.scenarioId) return;
    const s = scenarioById.get(runningRun.scenarioId);
    if (!s) return;
    const total = s.result.timeline.length;
    const timer = window.setTimeout(
      () => dispatch({ type: "tick", runId: runningRun.id, totalSteps: total }),
      replayDelay(s.result.timeline[runningRun.revealed], reducedMotion),
    );
    return () => window.clearTimeout(timer);
  }, [runningRun, scenarioById, reducedMotion]);

  // Keep the newest output in view while a run streams in.
  useEffect(() => {
    threadEnd.current?.scrollIntoView({
      behavior: reducedMotion ? "auto" : "smooth",
      block: "end",
    });
  }, [thread.length, runningRun?.revealed, reducedMotion]);

  function openConversation(id: string) {
    const scenarioId = conversationScenario[id];
    const s = scenarioId ? scenarioById.get(scenarioId) : undefined;
    dispatch({
      type: "open_conversation",
      conversationId: id,
      scenario: s,
      question: s?.question ?? "",
    });
    setListOpen(false);
  }

  function followUpsFor(run: ThreadRun): SampleScenario[] {
    const asked = new Set(thread.map((r) => r.scenarioId));
    return datasetScenarios
      .filter((s) => !asked.has(s.id) && s.id !== run.scenarioId && s.outcome !== "partial")
      .slice(0, 3);
  }

  const list = (
    <ConversationList
      conversations={state.conversations}
      activeId={state.activeConversationId}
      datasets={datasets}
      now={now}
      onSelect={openConversation}
      onNew={() => {
        dispatch({ type: "new_conversation" });
        setListOpen(false);
      }}
    />
  );

  return (
    <div className="grid h-[calc(100dvh-56px)] lg:h-dvh lg:grid-cols-[248px_minmax(0,1fr)] xl:grid-cols-[248px_minmax(0,1fr)_340px]">
      <aside
        aria-label="Conversation history"
        className="hidden min-h-0 border-r border-line bg-warm lg:block"
      >
        {list}
      </aside>

      <section aria-label="Analyst" className="flex min-h-0 min-w-0 flex-col">
        <div className="flex h-14 shrink-0 items-center justify-between gap-3 border-b border-line bg-warm/95 px-4 sm:px-6">
          <div className="flex min-w-0 items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              className="lg:hidden"
              onClick={() => setListOpen(true)}
              leadingIcon={<MessagesSquare className="size-4" aria-hidden />}
            >
              <span className="sr-only sm:not-sr-only">Conversations</span>
            </Button>
            <label htmlFor="dataset-select" className="sr-only">
              Dataset
            </label>
            <div className="relative">
              <Database
                className="pointer-events-none absolute top-1/2 left-2.5 z-[1] size-3.5 -translate-y-1/2 text-ink-3"
                aria-hidden
              />
              <Select
                id="dataset-select"
                value={state.datasetId}
                onChange={(e) => dispatch({ type: "select_dataset", datasetId: e.target.value })}
                disabled={Boolean(runningRun)}
                size="sm"
                className="w-[200px] pl-8 sm:w-[230px]"
              >
                {datasets.map((d) => (
                  <option key={d.id} value={d.id} disabled={d.status !== "ready"}>
                    {d.name}
                    {d.status !== "ready"
                      ? ` (${d.status === "loading" ? "loading" : "unavailable"})`
                      : ""}
                  </option>
                ))}
              </Select>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="hidden sm:block">
              <Badge tone="warning">Demo · sample runs</Badge>
            </span>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => dispatch({ type: "new_conversation" })}
              leadingIcon={<Plus className="size-4" aria-hidden />}
              className="lg:hidden"
            >
              New
            </Button>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-[820px] px-4 py-8 sm:px-6">
            {thread.length === 0 ? (
              <WelcomePanel
                scenarios={datasetScenarios}
                datasetName={datasetName(state.datasetId)}
                onAsk={ask}
              />
            ) : (
              <div className="grid gap-12">
                {thread.map((run, i) => (
                  <div
                    key={run.id}
                    onFocusCapture={() => dispatch({ type: "focus_run", runId: run.id })}
                    onMouseEnter={() =>
                      run.id !== state.focusedRunId &&
                      dispatch({ type: "focus_run", runId: run.id })
                    }
                    className={cn(i > 0 && "border-t border-line pt-10")}
                  >
                    <RunView
                      run={run}
                      scenario={run.scenarioId ? scenarioById.get(run.scenarioId) : undefined}
                      datasetName={datasetName(run.datasetId)}
                      samples={datasetScenarios}
                      followUps={i === thread.length - 1 ? followUpsFor(run) : []}
                      onCancel={() => dispatch({ type: "cancel", runId: run.id })}
                      onAsk={ask}
                    />
                  </div>
                ))}
              </div>
            )}
            <div ref={threadEnd} />
          </div>
        </div>

        <div className="shrink-0 border-t border-line bg-warm px-4 pt-3 pb-4 sm:px-6">
          <div className="mx-auto max-w-[820px]">
            <Composer
              onSubmit={ask}
              disabled={Boolean(runningRun)}
              disabledReason="Wait for the current analysis to finish, or cancel it."
              placeholder={
                thread.length > 0
                  ? "Ask a follow-up question…"
                  : `Ask a question about ${datasetName(state.datasetId)}…`
              }
            />
          </div>
        </div>
      </section>

      <aside
        aria-label="Agent execution"
        className="hidden min-h-0 flex-col border-l border-line bg-paper xl:flex"
      >
        <Inspector
          run={focused}
          scenario={focused?.scenarioId ? scenarioById.get(focused.scenarioId) : undefined}
        />
      </aside>

      <Drawer
        open={listOpen}
        onClose={() => setListOpen(false)}
        title="Conversations"
        side="left"
        widthClassName="w-[300px] bg-warm"
      >
        {list}
      </Drawer>
    </div>
  );
}

function WelcomePanel({
  scenarios,
  datasetName,
  onAsk,
}: {
  scenarios: SampleScenario[];
  datasetName: string;
  onAsk: (q: string) => void;
}) {
  return (
    <div className="pt-6 sm:pt-12">
      <p className="eyebrow">Analyst · {datasetName}</p>
      <h1 className="mt-3 text-display text-[34px] text-navy sm:text-[40px]">
        What would you like to know?
      </h1>
      <p className="mt-3 max-w-xl text-[15px] leading-6 text-ink-2">
        Ask in plain language. You’ll see the plan, every query and its validation, the results, and
        insights that cite their evidence.
      </p>
      {scenarios.length > 0 ? (
        <div className="mt-10">
          <p className="mb-3 text-[13px] font-medium text-ink">Example questions</p>
          <ul className="grid gap-2 sm:grid-cols-2">
            {scenarios.map((s) => (
              <li key={s.id}>
                <button
                  type="button"
                  onClick={() => onAsk(s.question)}
                  className="group grid h-full w-full gap-1.5 rounded-sm border border-line bg-paper px-4 py-3.5 text-left transition-colors duration-150 hover:border-forest/50 hover:bg-sage-50"
                >
                  <span className="text-2xs font-medium tracking-[0.06em] text-ink-2 uppercase group-hover:text-forest">
                    {s.shortLabel}
                  </span>
                  <span className="text-sm leading-5 text-ink">{s.question}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <EmptyState
          className="mt-8 rounded-md border border-dashed border-line-strong"
          icon={<Database className="size-5" aria-hidden />}
          title="No sample runs for this dataset"
          description="Recorded examples exist for the Retail demo dataset. Live analysis of any dataset arrives when this workspace is connected to the agent."
        />
      )}
    </div>
  );
}

function Inspector({
  run,
  scenario,
}: {
  run: ThreadRun | undefined;
  scenario: SampleScenario | undefined;
}) {
  if (!run || !scenario) {
    return (
      <div className="flex h-full flex-col">
        <InspectorHeader />
        <EmptyState
          icon={<Activity className="size-5" aria-hidden />}
          title={run ? "No execution trace" : "Nothing running yet"}
          description={
            run
              ? "This question wasn’t run, so there are no agent steps to show."
              : "When you ask a question, each agent step appears here as it happens: schema lookups, SQL validation, execution and verification."
          }
        />
      </div>
    );
  }
  const { result } = scenario;
  const total = result.timeline.reduce((acc, t) => acc + t.durationMs, 0);
  return (
    <div className="flex h-full min-h-0 flex-col">
      <InspectorHeader />
      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
        <p className="line-clamp-2 text-[13px] leading-5 text-ink-2">{run.question}</p>
        <div className="mt-5">
          <ExecutionTimeline
            steps={result.timeline}
            revealed={run.revealed}
            live={run.status === "running"}
            cancelled={run.status === "cancelled"}
          />
        </div>
      </div>
      <dl className="grid shrink-0 grid-cols-2 gap-px border-t border-line bg-line text-xs">
        {[
          ["Duration", formatDuration(total)],
          ["Model calls", String(result.usage.llmCalls)],
          ["SQL executed", String(result.usage.sqlExecutions)],
          ["Tokens", result.usage.tokens.toLocaleString("en-US")],
        ]
          // Totals are only meaningful once the run has finished.
          .map(([k, v]) => [k, run.status === "done" ? v : "—"])
          .map(([k, v]) => (
            <div key={k} className="bg-paper px-5 py-3">
              <dt className="text-ink-2">{k}</dt>
              <dd className="mt-0.5 font-mono text-[13px] text-ink tabular">{v}</dd>
            </div>
          ))}
      </dl>
    </div>
  );
}

function InspectorHeader() {
  return (
    <div className="flex h-14 shrink-0 items-center gap-2 border-b border-line px-5">
      <Activity className="size-4 text-forest" aria-hidden />
      <h2 className="text-[13px] font-semibold text-ink">Agent execution</h2>
    </div>
  );
}
