"use client";

import { History } from "lucide-react";
import { useState } from "react";

import { Badge, type Tone } from "@/components/ui/badge";
import { Button, ButtonLink } from "@/components/ui/button";
import { Drawer } from "@/components/ui/drawer";
import { Select } from "@/components/ui/field";
import { PageHeader } from "@/components/ui/layout";
import { EmptyState, ErrorState, Notice, Skeleton } from "@/components/ui/states";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { useToast } from "@/components/ui/toast";
import { SqlCode } from "@/features/analyst/sql-viewer";
import { datasets as datasetsApi, history } from "@/lib/api/endpoints";
import type { ApiError } from "@/lib/api/errors";
import type { ExecStatus, QueryHistoryItem, QueryOrigin } from "@/lib/api/types";
import { formatDateTime, formatInteger, formatRelative } from "@/lib/format";
import { errorMessage, useApi } from "@/lib/use-api";

const ORIGIN: Record<QueryOrigin, string> = {
  agent: "Analysis",
  preview: "Preview",
  widget_refresh: "Dashboard refresh",
  rerun: "Re-run",
};

const EXEC: Record<ExecStatus, { label: string; tone: Tone }> = {
  ok: { label: "Ran", tone: "positive" },
  error: { label: "Error", tone: "critical" },
  timeout: { label: "Timed out", tone: "warning" },
  cancelled: { label: "Cancelled", tone: "neutral" },
  not_run: { label: "Not run", tone: "neutral" },
};

export function QueryHistory() {
  const [origin, setOrigin] = useState<QueryOrigin | "">("");
  const [datasetId, setDatasetId] = useState("");
  const [openId, setOpenId] = useState<string | null>(null);
  const [more, setMore] = useState<{ items: QueryHistoryItem[]; cursor: string | null } | null>(
    null,
  );
  const [loadingMore, setLoadingMore] = useState(false);
  const { notify } = useToast();
  const datasetList = useApi(() => datasetsApi.list(), []);
  const first = useApi(
    () => history.queries({ origin, datasetId: datasetId || undefined }),
    [origin, datasetId],
  );
  const [firstSeen, setFirstSeen] = useState(first.data);
  if (firstSeen !== first.data) {
    setFirstSeen(first.data); // a new first page replaces anything loaded with "Load more"
    setMore(null);
  }

  const items = [...(first.data?.items ?? []), ...(more?.items ?? [])];
  const cursor = more ? more.cursor : (first.data?.next_cursor ?? null);
  const loading = first.loading || loadingMore;
  const error: ApiError | undefined = first.error;

  async function loadMore() {
    if (!cursor) return;
    setLoadingMore(true);
    try {
      const page = await history.queries({ origin, datasetId: datasetId || undefined, cursor });
      setMore((m) => ({ items: [...(m?.items ?? []), ...page.items], cursor: page.next_cursor }));
    } catch (e) {
      notify({ tone: "error", title: "Couldn’t load more", description: errorMessage(e) });
    } finally {
      setLoadingMore(false);
    }
  }

  const filtered = origin !== "" || datasetId !== "";
  const open = items.find((i) => i.id === openId);
  const now = new Date();

  return (
    <>
      <PageHeader
        eyebrow="Audit trail"
        title="Query history"
        description="Every SQL statement Sageboard ran against your data, with its outcome. Today that’s table previews; analysis queries will appear here too."
      />

      <div className="mt-8 flex flex-wrap items-center gap-2">
        <Select
          aria-label="Filter by source"
          value={origin}
          onChange={(e) => setOrigin(e.target.value as QueryOrigin | "")}
        >
          <option value="">All sources</option>
          {Object.entries(ORIGIN).map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
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
        {filtered ? (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setOrigin("");
              setDatasetId("");
            }}
          >
            Clear filters
          </Button>
        ) : null}
      </div>

      {error ? (
        <div className="mt-6 rounded-md border border-line bg-paper">
          <ErrorState
            title="Couldn’t load the history"
            description={error.message}
            code={error.code}
            action={
              <Button variant="secondary" onClick={first.reload}>
                Try again
              </Button>
            }
          />
        </div>
      ) : loading && items.length === 0 ? (
        <div
          className="mt-6 grid gap-2 rounded-md border border-line bg-paper p-5"
          aria-busy="true"
        >
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-9 w-full" />
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          className="mt-6 rounded-md border border-dashed border-line-strong"
          icon={<History className="size-5" aria-hidden />}
          title={filtered ? "Nothing matches these filters" : "No queries yet"}
          description={
            filtered
              ? "Try a different source or dataset."
              : "Open a table’s “Preview rows” on the Data sources page and the read-only query will be recorded here."
          }
          action={
            filtered ? null : (
              <ButtonLink href="/app/data" variant="secondary">
                Go to data sources
              </ButtonLink>
            )
          }
        />
      ) : (
        <>
          <div className="mt-6 overflow-x-auto rounded-md border border-line bg-paper">
            <Table>
              <caption className="sr-only">SQL statements</caption>
              <THead>
                <tr>
                  <TH>Statement</TH>
                  <TH className="hidden md:table-cell">Dataset</TH>
                  <TH>Outcome</TH>
                  <TH align="right" className="hidden sm:table-cell">
                    Rows
                  </TH>
                  <TH align="right" className="hidden sm:table-cell">
                    Time
                  </TH>
                  <TH align="right">When</TH>
                </tr>
              </THead>
              <tbody>
                {items.map((item) => (
                  <TR key={item.id} interactive onClick={() => setOpenId(item.id)}>
                    <TD className="max-w-[28rem]">
                      <button
                        type="button"
                        onClick={() => setOpenId(item.id)}
                        className="block w-full truncate text-left font-mono text-[12.5px] text-ink focus-visible:underline"
                      >
                        {item.executed_sql ?? "—"}
                      </button>
                      <p className="text-2xs text-ink-2">{ORIGIN[item.origin]}</p>
                    </TD>
                    <TD className="hidden text-ink-2 md:table-cell">{item.dataset_name}</TD>
                    <TD>
                      <Badge tone={EXEC[item.exec_status].tone} dot>
                        {EXEC[item.exec_status].label}
                      </Badge>
                    </TD>
                    <TD numeric className="hidden sm:table-cell">
                      {item.row_count != null ? formatInteger(item.row_count) : "—"}
                    </TD>
                    <TD numeric className="hidden sm:table-cell">
                      {item.exec_ms != null ? `${item.exec_ms} ms` : "—"}
                    </TD>
                    <TD align="right" className="text-ink-2">
                      {formatRelative(item.created_at, now)}
                    </TD>
                  </TR>
                ))}
              </tbody>
            </Table>
          </div>
          {cursor ? (
            <div className="mt-4 flex justify-center">
              <Button variant="secondary" onClick={() => void loadMore()} disabled={loading}>
                {loading ? "Loading…" : "Load more"}
              </Button>
            </div>
          ) : null}
        </>
      )}

      <Drawer
        open={Boolean(open)}
        onClose={() => setOpenId(null)}
        title={open ? `${ORIGIN[open.origin]} query` : "Query"}
        description={open ? `${open.dataset_name} · ${formatDateTime(open.created_at)}` : undefined}
        widthClassName="w-[min(640px,100vw)]"
      >
        {open ? (
          <div className="grid gap-5 px-5 py-5">
            <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-[13px] sm:grid-cols-4">
              <div>
                <dt className="text-ink-2">Outcome</dt>
                <dd className="mt-0.5 text-ink">{EXEC[open.exec_status].label}</dd>
              </div>
              <div>
                <dt className="text-ink-2">Rows</dt>
                <dd className="mt-0.5 text-ink tabular">
                  {open.row_count != null ? formatInteger(open.row_count) : "—"}
                  {open.truncated ? "+" : ""}
                </dd>
              </div>
              <div>
                <dt className="text-ink-2">Time</dt>
                <dd className="mt-0.5 text-ink tabular">
                  {open.exec_ms != null ? `${open.exec_ms} ms` : "—"}
                </dd>
              </div>
              <div>
                <dt className="text-ink-2">Validation</dt>
                <dd className="mt-0.5 text-ink">
                  {open.guard_status === "not_applicable"
                    ? "Built by Sageboard"
                    : open.guard_status}
                </dd>
              </div>
            </dl>
            {open.error_message ? (
              <Notice tone="error" title={open.error_code ?? "Error"}>
                {open.error_message}
              </Notice>
            ) : null}
            {open.executed_sql ? (
              <div className="overflow-hidden rounded-sm border border-line">
                <SqlCode sql={open.executed_sql} />
              </div>
            ) : null}
            <p className="text-xs text-ink-2">
              Ran on a read-only connection, inside your dataset’s own schema, with a statement
              timeout.
            </p>
          </div>
        ) : null}
      </Drawer>
    </>
  );
}
