"use client";

import { ArrowUpRight, History, RotateCcw, Search, X } from "lucide-react";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button, ButtonLink } from "@/components/ui/button";
import { Drawer } from "@/components/ui/drawer";
import { Input, Select } from "@/components/ui/field";
import { PageHeader } from "@/components/ui/layout";
import { EmptyState, Notice } from "@/components/ui/states";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { useToast } from "@/components/ui/toast";
import { RUN_STATUS } from "@/features/dashboard/dashboard-tables";
import { SqlCode } from "@/features/analyst/sql-viewer";
import { formatDateTime, formatDuration, formatRelative } from "@/lib/format";
import type { Dataset, HistoryEntry, RunStatus } from "@/types/domain";

const STATUS_FILTERS: Array<{ value: RunStatus | "all"; label: string }> = [
  { value: "all", label: "All statuses" },
  { value: "succeeded", label: "Answered" },
  { value: "partial", label: "Partial" },
  { value: "failed", label: "Failed" },
  { value: "cancelled", label: "Cancelled" },
];

export function QueryHistory({
  entries,
  datasets,
  nowIso,
}: {
  entries: readonly HistoryEntry[];
  datasets: readonly Dataset[];
  nowIso: string;
}) {
  const now = new Date(nowIso);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<RunStatus | "all">("all");
  const [datasetId, setDatasetId] = useState("all");
  const [openId, setOpenId] = useState<string | null>(null);
  const datasetName = (id: string) => datasets.find((d) => d.id === id)?.name ?? id;

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return entries.filter(
      (e) =>
        (status === "all" || e.status === status) &&
        (datasetId === "all" || e.datasetId === datasetId) &&
        (!q || e.question.toLowerCase().includes(q)),
    );
  }, [entries, query, status, datasetId]);

  const hasFilters = query !== "" || status !== "all" || datasetId !== "all";
  const open = entries.find((e) => e.id === openId);

  return (
    <>
      <PageHeader
        eyebrow="Audit trail"
        title="Query history"
        description="Every question, the SQL that ran and how it ended. Nothing is hidden, including failed attempts."
      />

      <div className="mt-8 flex flex-wrap items-center gap-2">
        <div className="relative w-full sm:w-80">
          <Search
            className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-3"
            aria-hidden
          />
          <Input
            type="search"
            aria-label="Search questions"
            placeholder="Search questions"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="pl-9"
          />
        </div>
        <Select
          aria-label="Filter by status"
          value={status}
          onChange={(e) => setStatus(e.target.value as RunStatus | "all")}
        >
          {STATUS_FILTERS.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </Select>
        <Select
          aria-label="Filter by dataset"
          value={datasetId}
          onChange={(e) => setDatasetId(e.target.value)}
        >
          <option value="all">All datasets</option>
          {datasets.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </Select>
        {hasFilters ? (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setQuery("");
              setStatus("all");
              setDatasetId("all");
            }}
            leadingIcon={<X className="size-3.5" aria-hidden />}
          >
            Clear
          </Button>
        ) : null}
        <p className="ml-auto text-xs text-ink-2 tabular" aria-live="polite">
          {filtered.length} of {entries.length} runs
        </p>
      </div>

      <div className="mt-4 overflow-hidden rounded-md border border-line bg-paper">
        {filtered.length === 0 ? (
          <EmptyState
            icon={<History className="size-5" aria-hidden />}
            title="No runs match these filters"
            description="Try a different search term or clear the filters."
            action={
              <Button
                variant="secondary"
                onClick={() => {
                  setQuery("");
                  setStatus("all");
                  setDatasetId("all");
                }}
              >
                Clear filters
              </Button>
            }
          />
        ) : (
          <Table>
            <caption className="sr-only">Query history</caption>
            <THead>
              <tr>
                <TH>Question</TH>
                <TH className="hidden lg:table-cell">Dataset</TH>
                <TH>Status</TH>
                <TH align="right" className="hidden md:table-cell">
                  Queries
                </TH>
                <TH align="right" className="hidden md:table-cell">
                  Duration
                </TH>
                <TH align="right">When</TH>
              </tr>
            </THead>
            <tbody>
              {filtered.map((e) => (
                <TR key={e.id} interactive onClick={() => setOpenId(e.id)}>
                  <TD className="max-w-[460px]">
                    <button
                      type="button"
                      onClick={() => setOpenId(e.id)}
                      className="line-clamp-2 text-left text-ink hover:text-forest focus-visible:underline"
                    >
                      {e.question}
                    </button>
                    <span className="font-mono text-2xs text-ink-3">{e.id}</span>
                  </TD>
                  <TD className="hidden text-ink-2 lg:table-cell">{datasetName(e.datasetId)}</TD>
                  <TD>
                    <Badge tone={RUN_STATUS[e.status].tone} dot>
                      {RUN_STATUS[e.status].label}
                    </Badge>
                  </TD>
                  <TD numeric className="hidden md:table-cell">
                    {e.queryCount}
                  </TD>
                  <TD numeric className="hidden md:table-cell">
                    {e.durationMs !== null ? formatDuration(e.durationMs) : "—"}
                  </TD>
                  <TD align="right" className="whitespace-nowrap text-ink-2">
                    {formatRelative(e.createdAt, now)}
                  </TD>
                </TR>
              ))}
            </tbody>
          </Table>
        )}
      </div>

      <HistoryDrawer
        entry={open}
        datasetName={open ? datasetName(open.datasetId) : ""}
        onClose={() => setOpenId(null)}
      />
    </>
  );
}

function HistoryDrawer({
  entry,
  datasetName,
  onClose,
}: {
  entry: HistoryEntry | undefined;
  datasetName: string;
  onClose: () => void;
}) {
  const { notify } = useToast();
  return (
    <Drawer
      open={Boolean(entry)}
      onClose={onClose}
      title="Run details"
      description={entry ? `${entry.id} · ${formatDateTime(entry.createdAt)}` : undefined}
      footer={
        entry ? (
          <div className="flex justify-end gap-2">
            <Button
              variant="ghost"
              leadingIcon={<RotateCcw className="size-3.5" aria-hidden />}
              onClick={() =>
                notify({
                  tone: "info",
                  title: "Re-run needs the live agent",
                  description: "Available once the backend is connected.",
                })
              }
            >
              Re-run
            </Button>
            {entry.scenarioId ? (
              <ButtonLink
                href={`/app/analyst?sample=${entry.scenarioId}`}
                variant="primary"
                trailingIcon={<ArrowUpRight className="size-4" aria-hidden />}
              >
                Open in analyst
              </ButtonLink>
            ) : null}
          </div>
        ) : null
      }
    >
      {entry ? (
        <div className="grid gap-6 px-5 py-5">
          <div>
            <p className="mb-1.5 eyebrow">Question</p>
            <p className="text-title text-[19px] text-ink">{entry.question}</p>
          </div>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-[13px] sm:grid-cols-4">
            {[
              [
                "Status",
                <Badge key="s" tone={RUN_STATUS[entry.status].tone} dot>
                  {RUN_STATUS[entry.status].label}
                </Badge>,
              ],
              ["Dataset", datasetName],
              ["Duration", entry.durationMs !== null ? formatDuration(entry.durationMs) : "—"],
              ["Rows", entry.rowCount ?? "—"],
            ].map(([k, v]) => (
              <div key={String(k)}>
                <dt className="text-xs text-ink-2">{k}</dt>
                <dd className="mt-1 text-ink tabular">{v}</dd>
              </div>
            ))}
          </dl>
          {entry.failureReason ? (
            <Notice
              tone={entry.status === "failed" ? "error" : "warning"}
              title={entry.status === "cancelled" ? "Cancelled" : "Why it didn’t complete"}
            >
              {entry.failureReason}
            </Notice>
          ) : null}
          {entry.sql ? (
            <div>
              <p className="mb-2 eyebrow">Executed SQL</p>
              <div className="overflow-hidden rounded-sm border border-line">
                <SqlCode sql={entry.sql} />
              </div>
            </div>
          ) : (
            <p className="text-[13px] text-ink-2">No query reached the database for this run.</p>
          )}
        </div>
      ) : null}
    </Drawer>
  );
}
