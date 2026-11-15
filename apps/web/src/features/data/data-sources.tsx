"use client";

import { Database, Eye, EyeOff, Loader2, Pencil, Sparkles, Trash2, Upload } from "lucide-react";
import { useState } from "react";

import { Badge, type Tone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/field";
import { PageHeader } from "@/components/ui/layout";
import { EmptyState, ErrorState, Notice, Skeleton } from "@/components/ui/states";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { Segmented, Tabs } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
import { datasets } from "@/lib/api/endpoints";
import type {
  DatasetColumn,
  DatasetDetail,
  DatasetStatus,
  DatasetSummary,
  DatasetTable,
} from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatBytes, formatInteger, formatPercent, formatRelative } from "@/lib/format";
import { errorMessage, useApi } from "@/lib/use-api";

import { UploadDrawer } from "./upload-drawer";

export const DATASET_STATUS: Record<DatasetStatus, { label: string; tone: Tone }> = {
  ready: { label: "Ready", tone: "positive" },
  loading: { label: "Loading", tone: "info" },
  failed: { label: "Failed", tone: "critical" },
  pending_review: { label: "Not confirmed", tone: "warning" },
  deleting: { label: "Deleting", tone: "neutral" },
};

const SOURCE: Record<DatasetSummary["source_type"], string> = {
  demo: "Sample",
  upload_csv: "CSV upload",
};

export function DataSources() {
  const list = useApi(() => datasets.list(), []);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [loadingSample, setLoadingSample] = useState(false);
  const { notify } = useToast();
  const items = list.data ?? [];
  const selected = items.find((d) => d.id === selectedId) ?? items[0];
  const hasSample = items.some((d) => d.source_type === "demo");

  async function loadSample() {
    setLoadingSample(true);
    try {
      const { dataset, created } = await datasets.loadSample();
      notify({
        tone: "success",
        title: created ? "Sample dataset loaded" : "Sample dataset already loaded",
        description: `${formatInteger(dataset.total_rows ?? 0)} rows across ${dataset.tables.length} tables.`,
      });
      setSelectedId(dataset.id);
      list.reload();
    } catch (error) {
      notify({
        tone: "error",
        title: "Couldn’t load the sample",
        description: errorMessage(error),
      });
    } finally {
      setLoadingSample(false);
    }
  }

  const sampleButton = (variant: "secondary" | "primary") => (
    <Button
      variant={variant}
      onClick={() => void loadSample()}
      disabled={loadingSample}
      leadingIcon={
        loadingSample ? (
          <Loader2 className="size-4 animate-spin" aria-hidden />
        ) : (
          <Sparkles className="size-4" aria-hidden />
        )
      }
    >
      {loadingSample ? "Loading sample…" : "Load sample dataset"}
    </Button>
  );

  return (
    <>
      <PageHeader
        eyebrow="Workspace"
        title="Data sources"
        description="Datasets you can analyse. Each lives in its own isolated schema and is only ever queried read-only."
        actions={
          <div className="flex flex-wrap gap-2">
            {!hasSample && items.length > 0 ? sampleButton("secondary") : null}
            <Button
              variant="primary"
              onClick={() => setUploadOpen(true)}
              leadingIcon={<Upload className="size-4" aria-hidden />}
            >
              Upload CSV
            </Button>
          </div>
        }
      />

      {list.loading && !list.data ? (
        <div
          className="mt-8 grid gap-2 rounded-md border border-line bg-paper p-5"
          aria-busy="true"
        >
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-9 w-full" />
        </div>
      ) : list.error ? (
        <div className="mt-8 rounded-md border border-line bg-paper">
          <ErrorState
            title="Couldn’t load your datasets"
            description={list.error.message}
            code={list.error.code}
            action={
              <Button variant="secondary" onClick={list.reload}>
                Try again
              </Button>
            }
          />
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          className="mt-10 rounded-md border border-dashed border-line-strong"
          icon={<Database className="size-5" aria-hidden />}
          title="No datasets yet"
          description="Upload a CSV of your own, or load the sample e-commerce dataset (customers, orders, products, payments) to explore Sageboard."
          action={
            <div className="flex flex-wrap justify-center gap-2">
              {sampleButton("primary")}
              <Button variant="secondary" onClick={() => setUploadOpen(true)}>
                Upload CSV
              </Button>
            </div>
          }
        />
      ) : (
        <>
          <DatasetList items={items} selectedId={selected?.id ?? null} onSelect={setSelectedId} />
          {selected ? (
            <DatasetPanel
              key={selected.id}
              summary={selected}
              onDeleted={() => {
                setSelectedId(null);
                list.reload();
              }}
              onChanged={list.reload}
            />
          ) : null}
        </>
      )}

      <UploadDrawer
        open={uploadOpen}
        onClose={() => {
          setUploadOpen(false);
          list.reload();
        }}
        onLoaded={(dataset) => {
          setSelectedId(dataset.id);
          list.reload();
        }}
      />
    </>
  );
}

function DatasetList({
  items,
  selectedId,
  onSelect,
}: {
  items: DatasetSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const now = new Date();
  return (
    <div className="mt-8 overflow-x-auto rounded-md border border-line bg-paper">
      <Table>
        <caption className="sr-only">Datasets</caption>
        <THead>
          <tr>
            <TH>Dataset</TH>
            <TH className="hidden md:table-cell">Source</TH>
            <TH>Status</TH>
            <TH align="right" className="hidden sm:table-cell">
              Rows
            </TH>
            <TH align="right" className="hidden lg:table-cell">
              Size
            </TH>
            <TH align="right" className="hidden md:table-cell">
              Updated
            </TH>
          </tr>
        </THead>
        <tbody>
          {items.map((d) => {
            const active = d.id === selectedId;
            return (
              <TR
                key={d.id}
                interactive
                className={cn(active && "bg-sage-50")}
                onClick={() => onSelect(d.id)}
              >
                <TD className={cn(active && "shadow-[inset_2px_0_0_var(--color-forest)]")}>
                  <button
                    type="button"
                    onClick={() => onSelect(d.id)}
                    aria-pressed={active}
                    className="text-left font-medium text-ink focus-visible:underline"
                  >
                    {d.name}
                  </button>
                  <p className="font-mono text-2xs text-ink-2">
                    {d.file_name ?? "generated sample"}
                  </p>
                </TD>
                <TD className="hidden text-ink-2 md:table-cell">{SOURCE[d.source_type]}</TD>
                <TD>
                  <Badge tone={DATASET_STATUS[d.status].tone} dot>
                    {d.status === "loading" ? (
                      <Loader2 className="size-3 animate-spin" aria-hidden />
                    ) : null}
                    {DATASET_STATUS[d.status].label}
                  </Badge>
                </TD>
                <TD numeric className="hidden sm:table-cell">
                  {d.total_rows ? formatInteger(d.total_rows) : "—"}
                </TD>
                <TD numeric className="hidden lg:table-cell">
                  {d.size_bytes ? formatBytes(d.size_bytes) : "—"}
                </TD>
                <TD align="right" className="hidden text-ink-2 md:table-cell">
                  {formatRelative(d.updated_at, now)}
                </TD>
              </TR>
            );
          })}
        </tbody>
      </Table>
    </div>
  );
}

function DatasetPanel({
  summary,
  onDeleted,
  onChanged,
}: {
  summary: DatasetSummary;
  onDeleted: () => void;
  onChanged: () => void;
}) {
  const detail = useApi(() => datasets.get(summary.id), [summary.id, summary.updated_at]);
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const { notify } = useToast();

  async function remove() {
    setDeleting(true);
    try {
      await datasets.remove(summary.id);
      notify({
        tone: "success",
        title: `Deleted “${summary.name}”`,
        description: "Its data and schema were removed.",
      });
      onDeleted();
    } catch (error) {
      notify({
        tone: "error",
        title: "Couldn’t delete the dataset",
        description: errorMessage(error),
      });
      setDeleting(false);
      setConfirming(false);
    }
  }

  const dataset = detail.data;
  return (
    <section aria-labelledby="dataset-heading" className="mt-10">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <p className="eyebrow">Dataset</p>
          <h2 id="dataset-heading" className="mt-1.5 text-title text-[24px] text-ink">
            {summary.name}
          </h2>
          {summary.description ? (
            <p className="mt-1 max-w-2xl text-sm text-ink-2">{summary.description}</p>
          ) : null}
        </div>
        <div className="flex items-center gap-3">
          {summary.status === "ready" && dataset ? (
            <p className="text-xs text-ink-2">
              {dataset.tables.length} {dataset.tables.length === 1 ? "table" : "tables"} · version{" "}
              {summary.version}
            </p>
          ) : null}
          {confirming ? (
            <div className="flex items-center gap-2" role="group" aria-label="Confirm deletion">
              <span className="text-[13px] text-ink-2">Delete this dataset and all its data?</span>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setConfirming(false)}
                disabled={deleting}
              >
                Cancel
              </Button>
              <Button size="sm" variant="danger" onClick={() => void remove()} disabled={deleting}>
                {deleting ? "Deleting…" : "Delete"}
              </Button>
            </div>
          ) : (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setConfirming(true)}
              leadingIcon={<Trash2 className="size-3.5" aria-hidden />}
            >
              Delete
            </Button>
          )}
        </div>
      </div>

      <div className="mt-5">
        {summary.status === "pending_review" ? (
          <Notice tone="warning" title="This upload was never confirmed">
            The file was checked but not loaded. Delete it and upload the file again to review its
            columns.
          </Notice>
        ) : summary.status === "failed" ? (
          <Notice tone="error" title="This dataset couldn’t be loaded">
            {summary.status_reason ?? "The load failed. Delete it and try the upload again."}
          </Notice>
        ) : detail.error ? (
          <div className="rounded-md border border-line bg-paper">
            <ErrorState
              title="Couldn’t load this dataset"
              description={detail.error.message}
              code={detail.error.code}
              action={
                <Button variant="secondary" onClick={detail.reload}>
                  Try again
                </Button>
              }
            />
          </div>
        ) : !dataset ? (
          <div className="grid gap-3 rounded-md border border-line bg-paper p-5" aria-busy="true">
            <Skeleton className="h-4 w-56" />
            <Skeleton className="h-28 w-full" />
          </div>
        ) : (
          <>
            {dataset.status_reason ? (
              <Notice tone="info" className="mb-4">
                {dataset.status_reason}
              </Notice>
            ) : null}
            <TablesView dataset={dataset} onChanged={onChanged} />
          </>
        )}
      </div>
    </section>
  );
}

function TablesView({ dataset, onChanged }: { dataset: DatasetDetail; onChanged: () => void }) {
  const [tableName, setTableName] = useState(dataset.tables[0]?.table_name ?? "");
  return (
    <div className="overflow-hidden rounded-md border border-line bg-paper">
      <Tabs
        label="Tables"
        value={tableName}
        onChange={setTableName}
        className="[&_[role=tablist]]:overflow-x-auto [&_[role=tablist]]:px-3"
        items={dataset.tables.map((t) => ({
          key: t.table_name,
          label: t.display_name,
          count: t.row_count,
        }))}
        renderPanel={(key) => {
          const table = dataset.tables.find((t) => t.table_name === key);
          return table ? (
            <TableView datasetId={dataset.id} table={table} onChanged={onChanged} />
          ) : null;
        }}
      />
    </div>
  );
}

function TableView({
  datasetId,
  table,
  onChanged,
}: {
  datasetId: string;
  table: DatasetTable;
  onChanged: () => void;
}) {
  const [view, setView] = useState<"columns" | "preview">("columns");
  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-2.5">
        <p className="text-[13px] text-ink-2">
          {table.description ?? (
            <>
              <span className="font-mono text-ink">{table.table_name}</span> ·{" "}
              {formatInteger(table.row_count)} rows
              {table.primary_key.length ? ` · key ${table.primary_key.join(", ")}` : ""}
            </>
          )}
        </p>
        <Segmented
          label="Table view"
          value={view}
          onChange={setView}
          options={[
            { key: "columns", label: "Columns" },
            { key: "preview", label: "Preview rows" },
          ]}
        />
      </div>
      {view === "columns" ? (
        <ColumnTable datasetId={datasetId} columns={table.columns} onChanged={onChanged} />
      ) : (
        <PreviewTable datasetId={datasetId} table={table.table_name} />
      )}
    </div>
  );
}

function profileSummary(c: DatasetColumn): string {
  if (c.is_sensitive) return "hidden (sensitive)";
  const top = c.profile.top_values ?? [];
  if (top.length) return top.map((v) => v.value).join(", ");
  if (c.profile.min != null) return `${c.profile.min} → ${c.profile.max}`;
  return (c.profile.examples ?? []).join(", ") || "—";
}

function ColumnTable({
  datasetId,
  columns,
  onChanged,
}: {
  datasetId: string;
  columns: DatasetColumn[];
  onChanged: () => void;
}) {
  const [rows, setRows] = useState(columns);
  const [source, setSource] = useState(columns);
  if (source !== columns) {
    // New data from the server (e.g. after a reload): adopt it during render.
    setSource(columns);
    setRows(columns);
  }
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const { notify } = useToast();

  async function save(
    column: DatasetColumn,
    patch: { description?: string | null; is_sensitive?: boolean },
  ) {
    setBusy(column.id);
    try {
      const updated = await datasets.updateColumn(datasetId, column.id, patch);
      setRows((current) => current.map((c) => (c.id === updated.id ? updated : c)));
      if (patch.is_sensitive !== undefined) onChanged();
      notify({
        tone: "success",
        title:
          patch.is_sensitive === undefined
            ? "Description saved"
            : patch.is_sensitive
              ? "Column hidden"
              : "Column visible",
        description:
          patch.is_sensitive === true
            ? "Its values are masked in previews and never shown to the analyst."
            : patch.is_sensitive === false
              ? "Sample values will appear after the next reload of the dataset."
              : "Used as context when analysing this dataset.",
      });
    } catch (error) {
      notify({
        tone: "error",
        title: "Couldn’t save the change",
        description: errorMessage(error),
      });
    } finally {
      setBusy(null);
      setEditing(null);
    }
  }

  return (
    <div className="overflow-x-auto">
      <Table>
        <THead>
          <tr>
            <TH>Column</TH>
            <TH>Type</TH>
            <TH className="hidden md:table-cell">Role</TH>
            <TH align="right">Distinct</TH>
            <TH align="right" className="hidden sm:table-cell">
              Empty
            </TH>
            <TH className="hidden lg:table-cell">Range / top values</TH>
            <TH className="min-w-56">Description</TH>
            <TH align="right">Visibility</TH>
          </tr>
        </THead>
        <tbody>
          {rows.map((c) => (
            <TR key={c.id}>
              <TD>
                <span className="font-mono text-[12.5px] text-ink">{c.column_name}</span>
                {c.is_primary_key ? <Badge className="ml-2">key</Badge> : null}
              </TD>
              <TD className="font-mono text-[12px] text-ink-2">{c.data_type}</TD>
              <TD className="hidden text-ink-2 md:table-cell">{c.semantic_role ?? "—"}</TD>
              <TD numeric>
                {c.profile.distinct_count != null ? formatInteger(c.profile.distinct_count) : "—"}
              </TD>
              <TD numeric className="hidden sm:table-cell">
                {c.profile.null_pct != null ? formatPercent(c.profile.null_pct) : "—"}
              </TD>
              <TD
                className={cn(
                  "hidden max-w-64 truncate text-[12.5px] lg:table-cell",
                  c.is_sensitive ? "text-ink-3 italic" : "text-ink-2",
                )}
              >
                {profileSummary(c)}
              </TD>
              <TD>
                {editing === c.id ? (
                  <form
                    className="flex gap-1.5"
                    onSubmit={(e) => {
                      e.preventDefault();
                      void save(c, { description: draft.trim() || null });
                    }}
                  >
                    <Input
                      aria-label={`Description for ${c.column_name}`}
                      className="h-8 text-[13px]"
                      value={draft}
                      maxLength={1000}
                      autoFocus
                      onChange={(e) => setDraft(e.target.value)}
                      onKeyDown={(e) => e.key === "Escape" && setEditing(null)}
                    />
                    <Button size="sm" type="submit" variant="primary" disabled={busy === c.id}>
                      Save
                    </Button>
                  </form>
                ) : (
                  <button
                    type="button"
                    onClick={() => {
                      setDraft(c.description ?? "");
                      setEditing(c.id);
                    }}
                    className="group flex w-full items-center justify-between gap-2 rounded-xs text-left text-[13px] text-ink-2 hover:text-ink"
                  >
                    <span className={cn(!c.description && "text-ink-3 italic")}>
                      {c.description || "Add a description"}
                    </span>
                    <Pencil
                      className="size-3.5 shrink-0 opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100"
                      aria-hidden
                    />
                  </button>
                )}
              </TD>
              <TD align="right">
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={busy === c.id}
                  onClick={() => void save(c, { is_sensitive: !c.is_sensitive })}
                  aria-label={
                    c.is_sensitive
                      ? `Show values of ${c.column_name}`
                      : `Hide values of ${c.column_name}`
                  }
                  leadingIcon={
                    c.is_sensitive ? (
                      <EyeOff className="size-3.5" aria-hidden />
                    ) : (
                      <Eye className="size-3.5" aria-hidden />
                    )
                  }
                >
                  {c.is_sensitive ? "Hidden" : "Visible"}
                </Button>
              </TD>
            </TR>
          ))}
        </tbody>
      </Table>
    </div>
  );
}

const PAGE = 25;

function PreviewTable({ datasetId, table }: { datasetId: string; table: string }) {
  const [offset, setOffset] = useState(0);
  const [reveal, setReveal] = useState(false);
  const preview = useApi(
    () => datasets.preview(datasetId, table, { limit: PAGE, offset, reveal }),
    [datasetId, table, offset, reveal],
  );
  const data = preview.data;

  if (preview.error) {
    return (
      <ErrorState
        title="Couldn’t load rows"
        description={preview.error.message}
        code={preview.error.code}
        action={
          <Button variant="secondary" onClick={preview.reload}>
            Try again
          </Button>
        }
      />
    );
  }
  if (!data) {
    return (
      <div className="grid gap-2 p-4" aria-busy="true">
        {Array.from({ length: 5 }, (_, i) => (
          <Skeleton key={i} className="h-6 w-full" />
        ))}
      </div>
    );
  }
  const hasSensitive = data.columns.some((c) => c.is_sensitive);
  return (
    <div aria-busy={preview.loading}>
      <div className="overflow-x-auto">
        <Table>
          <THead>
            <tr>
              {data.columns.map((c) => (
                <TH
                  key={c.name}
                  align={
                    ["integer", "bigint", "numeric"].includes(c.data_type) ? "right" : undefined
                  }
                >
                  <span className="font-mono text-[12px]">{c.name}</span>
                  {c.is_sensitive ? (
                    <EyeOff className="ml-1 inline size-3 text-ink-3" aria-label="sensitive" />
                  ) : null}
                </TH>
              ))}
            </tr>
          </THead>
          <tbody className={cn(preview.loading && "opacity-60")}>
            {data.rows.map((row, i) => (
              <TR key={offset + i}>
                {row.map((value, j) => {
                  const col = data.columns[j]!;
                  const masked = data.masked_columns.includes(col.name);
                  const numeric = ["integer", "bigint", "numeric"].includes(col.data_type);
                  return (
                    <TD
                      key={col.name}
                      numeric={numeric}
                      className={cn(
                        "max-w-64 truncate text-[12.5px]",
                        masked && "text-ink-3 italic",
                      )}
                    >
                      {value === null ? <span className="text-ink-3">null</span> : String(value)}
                    </TD>
                  );
                })}
              </TR>
            ))}
          </tbody>
        </Table>
      </div>
      {data.rows.length === 0 ? (
        <p className="px-4 py-6 text-sm text-ink-2">This table has no rows.</p>
      ) : null}
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line px-4 py-2.5 text-[13px] text-ink-2">
        <span>
          Rows {formatInteger(offset + 1)}–{formatInteger(offset + data.rows.length)} · read-only
          query in {data.exec_ms} ms
        </span>
        <div className="flex items-center gap-2">
          {hasSensitive ? (
            <Button size="sm" variant="ghost" onClick={() => setReveal((r) => !r)}>
              {reveal ? "Mask sensitive values" : "Show sensitive values"}
            </Button>
          ) : null}
          <Button
            size="sm"
            variant="secondary"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE))}
          >
            Previous
          </Button>
          <Button
            size="sm"
            variant="secondary"
            disabled={!data.has_more}
            onClick={() => setOffset(offset + PAGE)}
          >
            Next
          </Button>
        </div>
      </div>
    </div>
  );
}
