"use client";

import { Database, EyeOff, Loader2, Pencil, Upload } from "lucide-react";
import { useState } from "react";

import { Badge, type Tone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/field";
import { PageHeader } from "@/components/ui/layout";
import { Notice, Skeleton } from "@/components/ui/states";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { Tabs } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/cn";
import { formatBytes, formatInteger, formatPercent, formatRelative } from "@/lib/format";
import type { Dataset, DatasetColumn, DatasetStatus } from "@/types/domain";

import { UploadDrawer } from "./upload-drawer";

const STATUS: Record<DatasetStatus, { label: string; tone: Tone }> = {
  ready: { label: "Ready", tone: "positive" },
  loading: { label: "Loading", tone: "info" },
  failed: { label: "Failed", tone: "critical" },
  pending_review: { label: "Needs review", tone: "warning" },
};

const SOURCE: Record<Dataset["sourceType"], string> = {
  sample: "Sample",
  upload_csv: "CSV upload",
  upload_xlsx: "Excel upload",
};

export function DataSources({
  datasets,
  nowIso,
}: {
  datasets: readonly Dataset[];
  nowIso: string;
}) {
  const now = new Date(nowIso);
  const [selectedId, setSelectedId] = useState(datasets[0]?.id ?? null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const selected = datasets.find((d) => d.id === selectedId);

  return (
    <>
      <PageHeader
        eyebrow="Workspace"
        title="Data sources"
        description="Datasets the analyst can query. Each one is isolated and read only by the agent."
        actions={
          <Button
            variant="primary"
            onClick={() => setUploadOpen(true)}
            leadingIcon={<Upload className="size-4" aria-hidden />}
          >
            Upload dataset
          </Button>
        }
      />

      <div className="mt-8 overflow-hidden rounded-md border border-line bg-paper">
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
            {datasets.map((d) => {
              const active = d.id === selectedId;
              return (
                <TR
                  key={d.id}
                  interactive
                  className={cn(active && "bg-sage-50")}
                  onClick={() => setSelectedId(d.id)}
                >
                  <TD className={cn(active && "shadow-[inset_2px_0_0_var(--color-forest)]")}>
                    <button
                      type="button"
                      onClick={() => setSelectedId(d.id)}
                      aria-pressed={active}
                      className="text-left font-medium text-ink focus-visible:underline"
                    >
                      {d.name}
                    </button>
                    <p className="font-mono text-2xs text-ink-2">{d.fileName ?? "bundled"}</p>
                  </TD>
                  <TD className="hidden text-ink-2 md:table-cell">{SOURCE[d.sourceType]}</TD>
                  <TD>
                    <Badge tone={STATUS[d.status].tone} dot>
                      {d.status === "loading" ? (
                        <Loader2 className="size-3 animate-spin" aria-hidden />
                      ) : null}
                      {STATUS[d.status].label}
                    </Badge>
                  </TD>
                  <TD numeric className="hidden sm:table-cell">
                    {d.totalRows > 0 ? formatInteger(d.totalRows) : "—"}
                  </TD>
                  <TD numeric className="hidden lg:table-cell">
                    {formatBytes(d.sizeBytes)}
                  </TD>
                  <TD align="right" className="hidden text-ink-2 md:table-cell">
                    {formatRelative(d.updatedAt, now)}
                  </TD>
                </TR>
              );
            })}
          </tbody>
        </Table>
      </div>

      {selected ? (
        <DatasetDetail key={selected.id} dataset={selected} onUpload={() => setUploadOpen(true)} />
      ) : null}

      <UploadDrawer open={uploadOpen} onClose={() => setUploadOpen(false)} />
    </>
  );
}

function DatasetDetail({ dataset, onUpload }: { dataset: Dataset; onUpload: () => void }) {
  const [tableName, setTableName] = useState(dataset.tables[0]?.name ?? "");

  return (
    <section aria-labelledby="dataset-heading" className="mt-10">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">Dataset</p>
          <h2 id="dataset-heading" className="mt-1.5 text-title text-[24px] text-ink">
            {dataset.name}
          </h2>
          <p className="mt-1 max-w-2xl text-sm text-ink-2">{dataset.description}</p>
        </div>
        {dataset.status === "ready" ? (
          <p className="text-xs text-ink-2">
            {dataset.tables.length} tables · version {dataset.version} · read-only role{" "}
            <code className="text-ink">ds_…_r</code>
          </p>
        ) : null}
      </div>

      <div className="mt-5">
        {dataset.status === "loading" ? (
          <div className="grid gap-4 rounded-md border border-line bg-paper p-5" aria-busy="true">
            <Notice tone="info" title="Loading">
              {dataset.statusReason}
            </Notice>
            <Skeleton className="h-4 w-56" />
            <Skeleton className="h-28 w-full" />
          </div>
        ) : dataset.status === "failed" ? (
          <Notice
            tone="error"
            title="This dataset couldn’t be loaded"
            action={
              <Button size="sm" variant="secondary" onClick={onUpload}>
                Upload again
              </Button>
            }
          >
            {dataset.statusReason}
          </Notice>
        ) : (
          <div className="overflow-hidden rounded-md border border-line bg-paper">
            <Tabs
              label="Tables"
              value={tableName}
              onChange={setTableName}
              className="[&_[role=tablist]]:overflow-x-auto [&_[role=tablist]]:px-3"
              items={dataset.tables.map((t) => ({
                key: t.name,
                label: t.displayName,
                count: t.rowCount,
              }))}
              renderPanel={(key) => {
                const table = dataset.tables.find((t) => t.name === key);
                return table ? (
                  <ColumnTable columns={table.columns} description={table.description} />
                ) : null;
              }}
            />
          </div>
        )}
      </div>
    </section>
  );
}

function ColumnTable({
  columns,
  description,
}: {
  columns: DatasetColumn[];
  description: string | null;
}) {
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [editing, setEditing] = useState<string | null>(null);
  const { notify } = useToast();

  return (
    <div>
      {description ? (
        <p className="border-b border-line px-4 py-2.5 text-[13px] text-ink-2">{description}</p>
      ) : null}
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
          </tr>
        </THead>
        <tbody>
          {columns.map((c) => {
            const desc = edits[c.name] ?? c.description ?? "";
            return (
              <TR key={c.name}>
                <TD>
                  <span className="font-mono text-[12.5px] text-ink">{c.name}</span>
                  {c.isSensitive ? (
                    <Badge tone="warning" className="ml-2">
                      <EyeOff className="size-3" aria-hidden /> Masked
                    </Badge>
                  ) : null}
                </TD>
                <TD className="font-mono text-[12px] text-ink-2">{c.type}</TD>
                <TD className="hidden text-ink-2 md:table-cell">{c.semanticRole ?? "—"}</TD>
                <TD numeric>{formatInteger(c.profile.distinctCount)}</TD>
                <TD numeric className="hidden sm:table-cell">
                  {formatPercent(c.profile.nullPct)}
                </TD>
                <TD className="hidden max-w-64 truncate text-[12.5px] text-ink-2 lg:table-cell">
                  {c.profile.topValues.length
                    ? c.profile.topValues.map((v) => v.value).join(", ")
                    : c.profile.min !== null
                      ? `${c.profile.min} → ${c.profile.max}`
                      : "—"}
                </TD>
                <TD>
                  {editing === c.name ? (
                    <form
                      className="flex gap-1.5"
                      onSubmit={(e) => {
                        e.preventDefault();
                        setEditing(null);
                        notify({
                          tone: "success",
                          title: "Description saved",
                          description: "Used as context for the analyst (demo: not persisted).",
                        });
                      }}
                    >
                      <Input
                        aria-label={`Description for ${c.name}`}
                        className="h-8 text-[13px]"
                        value={desc}
                        onChange={(e) => setEdits({ ...edits, [c.name]: e.target.value })}
                        onKeyDown={(e) => e.key === "Escape" && setEditing(null)}
                      />
                      <Button size="sm" type="submit" variant="primary">
                        Save
                      </Button>
                    </form>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setEditing(c.name)}
                      className="group flex w-full items-center justify-between gap-2 rounded-xs text-left text-[13px] text-ink-2 hover:text-ink"
                    >
                      <span className={cn(!desc && "text-ink-3 italic")}>
                        {desc || "Add a description"}
                      </span>
                      <Pencil
                        className="size-3.5 shrink-0 opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100"
                        aria-hidden
                      />
                    </button>
                  )}
                </TD>
              </TR>
            );
          })}
        </tbody>
      </Table>
      {columns.length === 0 ? (
        <p className="flex items-center gap-2 px-4 py-6 text-sm text-ink-2">
          <Database className="size-4" aria-hidden /> No columns.
        </p>
      ) : null}
    </div>
  );
}
