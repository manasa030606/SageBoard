"use client";

import { FileDown, FileText, MessageSquarePlus, Search, SearchX } from "lucide-react";
import { useEffect, useState } from "react";

import { Badge, type Tone } from "@/components/ui/badge";
import { Button, ButtonLink } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/field";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/states";
import { useToast } from "@/components/ui/toast";
import { datasets as datasetsApi, history, reports } from "@/lib/api/endpoints";
import type { HistoryItem, SessionStatus } from "@/lib/api/types";
import { fileSlug, saveFile } from "@/lib/download";
import { formatInteger, formatRelative } from "@/lib/format";
import { errorMessage, toApiError, useApi } from "@/lib/use-api";

const STATUS: Record<SessionStatus, { label: string; tone: Tone }> = {
  succeeded: { label: "Answered", tone: "positive" },
  partial: { label: "Partial", tone: "warning" },
  failed: { label: "Failed", tone: "critical" },
  cancelled: { label: "Cancelled", tone: "neutral" },
  running: { label: "Running", tone: "info" },
  queued: { label: "Queued", tone: "info" },
  awaiting_input: { label: "Needs your answer", tone: "info" },
};

const RANGES = { "": "Any time", "7": "Last 7 days", "30": "Last 30 days", "90": "Last 90 days" };
type Range = keyof typeof RANGES;

const SEARCH_DELAY_MS = 300;
const DAY_MS = 86_400_000;

function sinceIso(range: Range): string | undefined {
  return range ? new Date(Date.now() - Number(range) * DAY_MS).toISOString() : undefined;
}

/** Past analyses: find one, reopen it, keep going in its conversation, save or download a report. */
export function AnalysisHistory() {
  const [text, setText] = useState("");
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<SessionStatus | "">("");
  const [datasetId, setDatasetId] = useState("");
  const [range, setRange] = useState<Range>("");
  const [more, setMore] = useState<{ items: HistoryItem[]; cursor: string | null } | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [reportIds, setReportIds] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const { notify } = useToast();

  useEffect(() => {
    const timer = window.setTimeout(() => setQ(text.trim()), SEARCH_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [text]);

  const datasetList = useApi(() => datasetsApi.list(), []);
  const filters = { q, status, datasetId, range };
  const first = useApi(
    () =>
      history.sessions({
        q: q || undefined,
        status,
        datasetId: datasetId || undefined,
        since: sinceIso(range),
      }),
    [q, status, datasetId, range],
  );
  const [firstSeen, setFirstSeen] = useState(first.data);
  if (firstSeen !== first.data) {
    setFirstSeen(first.data); // a new first page replaces anything loaded with "Load more"
    setMore(null);
  }

  const items = [...(first.data?.items ?? []), ...(more?.items ?? [])];
  const cursor = more ? more.cursor : (first.data?.next_cursor ?? null);
  const filtered = q !== "" || status !== "" || datasetId !== "" || range !== "";

  async function loadMore() {
    if (!cursor) return;
    setLoadingMore(true);
    try {
      const page = await history.sessions({
        cursor,
        q: filters.q || undefined,
        status: filters.status,
        datasetId: filters.datasetId || undefined,
        since: sinceIso(filters.range),
      });
      setMore((m) => ({ items: [...(m?.items ?? []), ...page.items], cursor: page.next_cursor }));
    } catch (e) {
      notify({ tone: "error", title: "Couldn’t load more", description: errorMessage(e) });
    } finally {
      setLoadingMore(false);
    }
  }

  async function saveReport(item: HistoryItem) {
    setBusy(`save-${item.id}`);
    try {
      const created = await reports.create(item.id);
      setReportIds((ids) => ({ ...ids, [item.id]: created.id }));
      notify({ tone: "success", title: "Saved as report", description: `“${created.title}”` });
    } catch (e) {
      notify({
        tone: "error",
        title: "Couldn’t save the report",
        description: toApiError(e).message,
      });
    } finally {
      setBusy(null);
    }
  }

  async function downloadPdf(item: HistoryItem, reportId: string) {
    setBusy(`pdf-${item.id}`);
    try {
      saveFile(fileSlug(item.question, "pdf"), await reports.pdf(reportId));
    } catch (e) {
      notify({ tone: "error", title: "Couldn’t download the PDF", description: errorMessage(e) });
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <div className="flex flex-wrap items-center gap-2" role="search">
        <div className="relative min-w-60 flex-1 sm:max-w-sm">
          <Search
            className="pointer-events-none absolute top-1/2 left-3 size-3.5 -translate-y-1/2 text-ink-3"
            aria-hidden
          />
          <Input
            type="search"
            aria-label="Search past analyses"
            placeholder="Search questions, answers and datasets"
            value={text}
            onChange={(e) => setText(e.target.value)}
            className="pl-9"
          />
        </div>
        <Select
          aria-label="Filter by outcome"
          value={status}
          onChange={(e) => setStatus(e.target.value as SessionStatus | "")}
        >
          <option value="">Any outcome</option>
          <option value="succeeded">Answered</option>
          <option value="partial">Partial</option>
          <option value="failed">Failed</option>
          <option value="cancelled">Cancelled</option>
        </Select>
        <Select
          aria-label="Filter by dataset"
          value={datasetId}
          onChange={(e) => setDatasetId(e.target.value)}
        >
          <option value="">All datasets</option>
          {(datasetList.data ?? []).map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </Select>
        <Select
          aria-label="Filter by date"
          value={range}
          onChange={(e) => setRange(e.target.value as Range)}
        >
          {Object.entries(RANGES).map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </Select>
        {filtered ? (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setText("");
              setQ("");
              setStatus("");
              setDatasetId("");
              setRange("");
            }}
          >
            Clear filters
          </Button>
        ) : null}
      </div>

      {first.error ? (
        <div className="mt-6 rounded-md border border-line bg-paper">
          <ErrorState
            title="Couldn’t load your analyses"
            description={first.error.message}
            code={first.error.code}
            action={
              <Button variant="secondary" onClick={first.reload}>
                Try again
              </Button>
            }
          />
        </div>
      ) : first.loading && items.length === 0 ? (
        <div className="mt-6 grid gap-3" aria-busy="true" aria-label="Loading analyses">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-28 w-full" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="mt-6 rounded-md border border-line bg-paper">
          <EmptyState
            icon={
              filtered ? (
                <SearchX className="size-5" aria-hidden />
              ) : (
                <MessageSquarePlus className="size-5" aria-hidden />
              )
            }
            title={filtered ? "No analyses match" : "No analyses yet"}
            description={
              filtered
                ? "Try a different search or clear the filters."
                : "Questions you ask the analyst are saved here, with their SQL, results and insights."
            }
            action={
              filtered ? undefined : (
                <ButtonLink href="/app/analyst" variant="primary">
                  Ask a question
                </ButtonLink>
              )
            }
          />
        </div>
      ) : (
        <ul className="mt-6 grid gap-3" aria-label="Past analyses">
          {items.map((item) => {
            const state = STATUS[item.status];
            const reportId = reportIds[item.id] ?? item.report_id;
            const finished = item.status === "succeeded" || item.status === "partial";
            const open = `/app/analyst?conversation=${item.conversation_id}&session=${item.id}`;
            return (
              <li key={item.id} className="rounded-md border border-line bg-paper p-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <h3 className="max-w-prose text-[15px] leading-6 font-medium text-ink">
                    {item.question}
                  </h3>
                  <Badge tone={state.tone} dot>
                    {state.label}
                  </Badge>
                </div>
                {item.summary ? (
                  <p className="mt-2 line-clamp-2 max-w-prose text-[13.5px] leading-6 text-ink-2">
                    {item.summary}
                  </p>
                ) : null}
                <p className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-2">
                  <span>{item.dataset_name}</span>
                  <span aria-hidden>·</span>
                  <span>{formatRelative(item.created_at, new Date())}</span>
                  {finished ? (
                    <>
                      <span aria-hidden>·</span>
                      <span className="tabular">
                        {formatInteger(item.finding_count)}{" "}
                        {item.finding_count === 1 ? "finding" : "findings"}
                      </span>
                      <span aria-hidden>·</span>
                      <span className="tabular">
                        {formatInteger(item.query_count)}{" "}
                        {item.query_count === 1 ? "query" : "queries"}
                      </span>
                    </>
                  ) : null}
                </p>
                <div className="mt-4 flex flex-wrap items-center gap-2">
                  <ButtonLink href={open} size="sm" variant="secondary">
                    Open analysis
                  </ButtonLink>
                  <ButtonLink
                    href={`/app/analyst?conversation=${item.conversation_id}`}
                    size="sm"
                    variant="ghost"
                    leadingIcon={<MessageSquarePlus className="size-3.5" aria-hidden />}
                  >
                    Continue conversation
                  </ButtonLink>
                  {reportId ? (
                    <>
                      <ButtonLink
                        href={`/app/reports/${reportId}`}
                        size="sm"
                        variant="ghost"
                        leadingIcon={<FileText className="size-3.5" aria-hidden />}
                      >
                        View report
                      </ButtonLink>
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={busy !== null}
                        leadingIcon={<FileDown className="size-3.5" aria-hidden />}
                        onClick={() => void downloadPdf(item, reportId)}
                      >
                        {busy === `pdf-${item.id}` ? "Preparing PDF…" : "Download PDF"}
                      </Button>
                    </>
                  ) : finished ? (
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={busy !== null}
                      leadingIcon={<FileText className="size-3.5" aria-hidden />}
                      onClick={() => void saveReport(item)}
                    >
                      {busy === `save-${item.id}` ? "Saving…" : "Save as report"}
                    </Button>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {cursor ? (
        <div className="mt-5 flex justify-center">
          <Button variant="secondary" onClick={() => void loadMore()} disabled={loadingMore}>
            {loadingMore ? "Loading…" : "Load more"}
          </Button>
        </div>
      ) : null}
    </>
  );
}
