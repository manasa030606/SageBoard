"use client";

import { Database, MessagesSquare, Plus } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Drawer } from "@/components/ui/drawer";
import { Select } from "@/components/ui/field";
import { EmptyState, ErrorState, Notice, Skeleton } from "@/components/ui/states";
import { conversations as conversationsApi, datasets as datasetsApi } from "@/lib/api/endpoints";
import type { SessionSummary } from "@/lib/api/types";
import { toApiError, useApi } from "@/lib/use-api";

import { Composer } from "../composer";
import { ConversationList } from "../conversation-list";
import { RunCard } from "./run-card";

export function LiveAnalystWorkspace() {
  const router = useRouter();
  const datasetsState = useApi(() => datasetsApi.list(), []);
  const ready = (datasetsState.data ?? []).filter((d) => d.status === "ready");
  const [datasetId, setDatasetId] = useState<string>("");
  // History links here with ?conversation=<id>&session=<id> to continue or reopen an analysis.
  const params = useSearchParams();
  const conversationParam = params.get("conversation");
  const focusSessionId = params.get("session");
  const linked = useApi(
    () => (conversationParam ? conversationsApi.get(conversationParam) : Promise.resolve(null)),
    [conversationParam],
  );
  const linkedDataset =
    linked.data && ready.some((d) => d.id === linked.data?.dataset_id) ? linked.data : null;
  const effectiveDataset = datasetId || linkedDataset?.dataset_id || ready[0]?.id || "";

  if (datasetsState.error) {
    return (
      <div className="mx-auto max-w-[760px] px-6 py-16">
        <ErrorState
          title="Couldn’t load your datasets"
          description={datasetsState.error.message}
          action={<Button onClick={datasetsState.reload}>Try again</Button>}
        />
      </div>
    );
  }
  if (datasetsState.loading && !datasetsState.data) {
    return (
      <div className="mx-auto grid max-w-[760px] gap-4 px-6 py-16" aria-busy="true">
        <Skeleton className="h-8 w-56" />
        <Skeleton className="h-28 w-full" />
      </div>
    );
  }
  if (conversationParam && linked.loading && !linked.data && !linked.error) {
    return (
      <div className="mx-auto grid max-w-[760px] gap-4 px-6 py-16" aria-busy="true">
        <Skeleton className="h-8 w-56" />
        <Skeleton className="h-28 w-full" />
      </div>
    );
  }
  if (ready.length === 0) {
    return (
      <div className="mx-auto max-w-[760px] px-6 py-16">
        <EmptyState
          icon={<Database className="size-5" aria-hidden />}
          title="No dataset is ready yet"
          description="Add the sample dataset or upload a CSV on the Data sources page, then come back to ask questions."
          action={
            <Button onClick={() => router.push("/app/data")} variant="primary">
              Open Data sources
            </Button>
          }
        />
      </div>
    );
  }
  return (
    <Thread
      key={effectiveDataset}
      datasetId={effectiveDataset}
      datasetName={ready.find((d) => d.id === effectiveDataset)?.name ?? "Dataset"}
      datasetOptions={ready.map((d) => ({ id: d.id, name: d.name }))}
      onDataset={setDatasetId}
      initialConversationId={
        linkedDataset && linkedDataset.dataset_id === effectiveDataset ? linkedDataset.id : null
      }
      focusSessionId={focusSessionId}
      linkError={conversationParam && linked.error ? linked.error.message : null}
    />
  );
}

function Thread({
  datasetId,
  datasetName,
  datasetOptions,
  onDataset,
  initialConversationId,
  focusSessionId,
  linkError,
}: {
  initialConversationId: string | null;
  focusSessionId: string | null;
  linkError: string | null;
  datasetId: string;
  datasetName: string;
  datasetOptions: { id: string; name: string }[];
  onDataset: (id: string) => void;
}) {
  const conversationsState = useApi(() => conversationsApi.list(datasetId), [datasetId]);
  const [activeId, setActiveId] = useState<string | null>(initialConversationId);
  const [optimistic, setOptimistic] = useState<SessionSummary[]>([]);
  const [asking, setAsking] = useState(false);
  const [askError, setAskError] = useState<string | null>(null);
  const [listOpen, setListOpen] = useState(false);
  const threadEnd = useRef<HTMLDivElement>(null);

  const conversationState = useApi(
    () => (activeId ? conversationsApi.get(activeId) : Promise.resolve(null)),
    [activeId],
  );
  const serverSessions = conversationState.data?.sessions ?? [];
  const serverIds = new Set(serverSessions.map((s) => s.id));
  const sessions = [...serverSessions, ...optimistic.filter((s) => !serverIds.has(s.id))];
  const busy = asking;

  // Reopening a past analysis: bring it into view once its thread has loaded.
  const scrolledTo = useRef<string | null>(null);
  useEffect(() => {
    if (!focusSessionId || scrolledTo.current === focusSessionId) return;
    if (!sessions.some((s) => s.id === focusSessionId)) return;
    scrolledTo.current = focusSessionId;
    requestAnimationFrame(() =>
      document.getElementById(`run-${focusSessionId}`)?.scrollIntoView({ block: "start" }),
    );
  });

  async function ask(question: string) {
    setAskError(null);
    setAsking(true);
    try {
      const conversationId = activeId ?? (await conversationsApi.create(datasetId)).id;
      const accepted = await conversationsApi.ask(conversationId, question);
      setActiveId(conversationId);
      setOptimistic((current) => [...current, accepted.session]);
      if (!accepted.agent_available) setAskError(accepted.message);
      conversationsState.reload();
      requestAnimationFrame(() => threadEnd.current?.scrollIntoView({ behavior: "smooth" }));
    } catch (err) {
      setAskError(toApiError(err).message);
    } finally {
      setAsking(false);
    }
  }

  const reloadConversations = conversationsState.reload;
  const onSettled = useCallback(() => {
    // Refresh titles ("New conversation" → first question) once a run finishes.
    reloadConversations();
  }, [reloadConversations]);

  const conversationItems = (conversationsState.data?.items ?? []).map((c) => ({
    id: c.id,
    title: c.title,
    updatedAt: c.updated_at,
  }));
  const anyActive = sessions.some((s) => s.status === "queued" || s.status === "running");

  return (
    <div className="grid h-full min-h-0 grid-cols-1 xl:grid-cols-[280px_1fr]">
      <aside className="hidden min-h-0 border-r border-line bg-warm xl:block">
        <ConversationList
          conversations={conversationItems}
          activeId={activeId}
          onSelect={(id) => setActiveId(id)}
          onNew={() => {
            setActiveId(null);
            setOptimistic([]);
          }}
        />
      </aside>

      <div className="flex min-h-0 flex-col">
        <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-2.5 sm:px-6">
          <div className="flex shrink-0 items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              className="xl:hidden"
              onClick={() => setListOpen(true)}
              leadingIcon={<MessagesSquare className="size-4" aria-hidden />}
            >
              Conversations
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="max-xl:hidden"
              onClick={() => {
                setActiveId(null);
                setOptimistic([]);
              }}
              leadingIcon={<Plus className="size-4" aria-hidden />}
            >
              New conversation
            </Button>
          </div>
          <label className="flex min-w-0 items-center gap-2 text-xs text-ink-2">
            <Database className="size-3.5" aria-hidden />
            Dataset
            <Select
              aria-label="Dataset"
              value={datasetId}
              onChange={(event) => onDataset(event.target.value)}
              className="max-w-44 min-w-0 sm:min-w-44"
            >
              {datasetOptions.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </Select>
          </label>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto grid max-w-[820px] gap-10 px-4 py-8 sm:px-6">
            {linkError ? (
              <Notice tone="warning" title="That conversation couldn’t be opened">
                {linkError} You can start a new one below.
              </Notice>
            ) : null}
            {activeId && conversationState.error ? (
              <ErrorState
                title="Couldn’t load this conversation"
                description={conversationState.error.message}
                action={<Button onClick={conversationState.reload}>Try again</Button>}
              />
            ) : null}
            {sessions.length === 0 && !conversationState.loading ? (
              <EmptyState
                icon={<MessagesSquare className="size-5" aria-hidden />}
                title={`Ask anything about “${datasetName}”`}
                description="The agent plans the analysis, writes and validates SQL, runs it read-only, and answers with verified, evidence-cited insights."
              />
            ) : null}
            {sessions.map((session, i) => (
              <div key={session.id} id={`run-${session.id}`} className="scroll-mt-6">
                <RunCard
                  sessionId={session.id}
                  question={session.question}
                  datasetName={datasetName}
                  onAsk={(q) => void ask(q)}
                  onSettled={i === sessions.length - 1 ? onSettled : undefined}
                  defaultOpen={
                    focusSessionId ? session.id === focusSessionId : i === sessions.length - 1
                  }
                />
              </div>
            ))}
            <div ref={threadEnd} />
          </div>
        </div>

        <div className="border-t border-line bg-warm/60 px-4 py-3 sm:px-6">
          <div className="mx-auto max-w-[820px]">
            {askError ? (
              <Notice tone="warning" title="The question was saved but not analysed">
                {askError}
              </Notice>
            ) : null}
            <Composer
              onSubmit={(q) => void ask(q)}
              disabled={busy || anyActive}
              disabledReason={anyActive ? "Wait for the current analysis to finish." : undefined}
              placeholder={`Ask about ${datasetName}… e.g. “Why did revenue decrease last month?”`}
            />
          </div>
        </div>
      </div>

      <Drawer open={listOpen} onClose={() => setListOpen(false)} title="Conversations" side="left">
        <ConversationList
          conversations={conversationItems}
          activeId={activeId}
          onSelect={(id) => {
            setActiveId(id);
            setListOpen(false);
          }}
          onNew={() => {
            setActiveId(null);
            setOptimistic([]);
            setListOpen(false);
          }}
        />
      </Drawer>
    </div>
  );
}
