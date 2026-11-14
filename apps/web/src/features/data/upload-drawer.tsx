"use client";

import { AlertTriangle, FileUp, UploadCloud } from "lucide-react";
import { useRef, useState, type DragEvent } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Drawer } from "@/components/ui/drawer";
import { Field, Input, Select } from "@/components/ui/field";
import { Notice } from "@/components/ui/states";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { useToast } from "@/components/ui/toast";
import { datasets } from "@/lib/api/endpoints";
import { ApiError } from "@/lib/api/errors";
import {
  COLUMN_TYPES,
  type ColumnType,
  type DatasetDetail,
  type UploadIssue,
  type UploadReview,
} from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { validateUpload } from "@/lib/csv-preview";
import { formatBytes, formatInteger } from "@/lib/format";

type Step =
  | { kind: "select"; error?: string; issues?: UploadIssue[] }
  | { kind: "chosen"; file: File }
  | { kind: "analysing"; file: File }
  | { kind: "review"; file: File; review: UploadReview; types: Record<string, ColumnType> }
  | { kind: "loading"; file: File; review: UploadReview; types: Record<string, ColumnType> }
  | { kind: "failed"; file: File; message: string };

function issuesFrom(error: unknown): UploadIssue[] | undefined {
  if (!(error instanceof ApiError)) return undefined;
  const issues = error.details["issues"];
  return Array.isArray(issues) ? (issues as UploadIssue[]) : undefined;
}

export function UploadDrawer({
  open,
  onClose,
  onLoaded,
}: {
  open: boolean;
  onClose: () => void;
  onLoaded: (dataset: DatasetDetail) => void;
}) {
  const [step, setStep] = useState<Step>({ kind: "select" });
  const [name, setName] = useState("");
  const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const { notify } = useToast();

  function reset() {
    setStep({ kind: "select" });
    setName("");
  }

  function close() {
    // A reviewed-but-unconfirmed upload is a pending dataset on the server: discard it.
    if (step.kind === "review") void datasets.remove(step.review.dataset.id).catch(() => undefined);
    reset();
    onClose();
  }

  function choose(file: File) {
    const error = validateUpload(file);
    if (error) {
      setStep({ kind: "select", error });
      return;
    }
    setName(
      file.name
        .replace(/\.csv$/i, "")
        .replace(/[_-]+/g, " ")
        .trim(),
    );
    setStep({ kind: "chosen", file });
  }

  async function analyse(file: File) {
    setStep({ kind: "analysing", file });
    try {
      const review = await datasets.upload(file, name);
      setStep({
        kind: "review",
        file,
        review,
        types: Object.fromEntries(review.columns.map((c) => [c.name, c.inferred_type])),
      });
    } catch (error) {
      setStep({
        kind: "select",
        error: error instanceof ApiError ? error.message : "The file couldn’t be uploaded.",
        issues: issuesFrom(error),
      });
    }
  }

  async function load(current: Extract<Step, { kind: "review" }>) {
    setStep({ ...current, kind: "loading" });
    const overrides = Object.fromEntries(
      current.review.columns
        .filter((c) => current.types[c.name] !== c.inferred_type)
        .map((c) => [c.name, current.types[c.name]!]),
    );
    try {
      const dataset = await datasets.finalize(current.review.dataset.id, overrides);
      notify({
        tone: "success",
        title: `“${dataset.name}” is ready`,
        description: `${formatInteger(dataset.total_rows ?? 0)} rows loaded.`,
      });
      onLoaded(dataset);
      reset();
      onClose();
    } catch (error) {
      setStep({
        kind: "failed",
        file: current.file,
        message: error instanceof ApiError ? error.message : "The dataset couldn’t be loaded.",
      });
    }
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    const file = event.dataTransfer.files[0];
    if (file) choose(file);
  }

  const footer =
    step.kind === "chosen" ? (
      <div className="flex items-center justify-between gap-3">
        <Button variant="ghost" onClick={reset}>
          Choose another file
        </Button>
        <Button variant="primary" onClick={() => void analyse(step.file)} disabled={!name.trim()}>
          Check file
        </Button>
      </div>
    ) : step.kind === "review" || step.kind === "loading" ? (
      <div className="flex items-center justify-between gap-3">
        <Button variant="ghost" onClick={close} disabled={step.kind === "loading"}>
          Discard
        </Button>
        <Button
          variant="primary"
          onClick={() => step.kind === "review" && void load(step)}
          disabled={step.kind === "loading"}
        >
          {step.kind === "loading"
            ? "Loading…"
            : `Load ${formatInteger(step.review.row_count)} rows`}
        </Button>
      </div>
    ) : step.kind === "failed" ? (
      <div className="flex justify-end">
        <Button variant="secondary" onClick={reset}>
          Upload another file
        </Button>
      </div>
    ) : null;

  return (
    <Drawer
      open={open}
      onClose={close}
      title="Upload a dataset"
      description="A UTF-8 CSV up to 25 MB. Sageboard checks it first; nothing is stored until you confirm the column types."
      widthClassName="w-[min(680px,100vw)]"
      footer={footer}
    >
      <div className="grid gap-5 px-5 py-5">
        {step.kind === "select" ? (
          <>
            {step.error ? (
              <Notice tone="error" title="That file can’t be used">
                {step.error}
                {step.issues?.length ? (
                  <ul className="mt-2 grid list-disc gap-1 pl-4">
                    {step.issues.slice(0, 8).map((issue, i) => (
                      <li key={`${issue.code}-${i}`}>{issue.message}</li>
                    ))}
                  </ul>
                ) : null}
              </Notice>
            ) : null}
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
              className={cn(
                "flex flex-col items-center rounded-md border border-dashed px-6 py-12 text-center transition-colors duration-150",
                dragging ? "border-forest bg-sage-50" : "border-line-strong bg-warm/50",
              )}
            >
              <UploadCloud className="size-7 text-forest" aria-hidden strokeWidth={1.5} />
              <p className="mt-3 text-sm font-medium text-ink">Drag a CSV file here</p>
              <p className="mt-1 text-[13px] text-ink-2">or</p>
              <Button
                className="mt-3"
                variant="secondary"
                onClick={() => input.current?.click()}
                leadingIcon={<FileUp className="size-4" aria-hidden />}
              >
                Browse files
              </Button>
              <input
                ref={input}
                type="file"
                accept=".csv,text/csv"
                className="sr-only"
                aria-label="Choose a CSV file"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) choose(file);
                  e.target.value = "";
                }}
              />
              <p className="mt-5 text-2xs text-ink-2">
                .csv (comma, semicolon, tab or pipe) · UTF-8 · max 25 MB · 200 columns · 1M rows
              </p>
            </div>
          </>
        ) : null}

        {step.kind !== "select" ? (
          <div className="flex items-center justify-between gap-3 rounded-sm border border-line bg-warm/50 px-3.5 py-2.5 text-[13px]">
            <span className="truncate font-medium text-ink">{step.file.name}</span>
            <span className="shrink-0 text-ink-2 tabular">{formatBytes(step.file.size)}</span>
          </div>
        ) : null}

        {step.kind === "chosen" ? (
          <Field label="Dataset name" hint="You can rename it later.">
            {({ id, describedBy }) => (
              <Input
                id={id}
                value={name}
                maxLength={120}
                aria-describedby={describedBy}
                onChange={(e) => setName(e.target.value)}
              />
            )}
          </Field>
        ) : null}

        {step.kind === "analysing" ? (
          <p role="status" className="text-sm text-ink-2">
            Checking {step.file.name}: encoding, columns, types and missing values…
          </p>
        ) : null}

        {step.kind === "failed" ? (
          <Notice tone="error" title="Nothing was loaded">
            {step.message}
          </Notice>
        ) : null}

        {step.kind === "review" || step.kind === "loading" ? (
          <Review
            review={step.review}
            types={step.types}
            disabled={step.kind === "loading"}
            onType={(column, type) =>
              step.kind === "review" &&
              setStep({ ...step, types: { ...step.types, [column]: type } })
            }
          />
        ) : null}
      </div>
    </Drawer>
  );
}

function Review({
  review,
  types,
  disabled,
  onType,
}: {
  review: UploadReview;
  types: Record<string, ColumnType>;
  disabled: boolean;
  onType: (column: string, type: ColumnType) => void;
}) {
  const warnings = review.issues.filter((i) => i.severity === "warning");
  return (
    <>
      <p className="text-sm text-ink-2">
        <span className="font-medium text-ink">{formatInteger(review.row_count)}</span> rows ·{" "}
        {review.columns.length} columns
        {review.rejected_count > 0 ? (
          <>
            {" "}
            ·{" "}
            <span className="text-amber-ink">
              {formatInteger(review.rejected_count)} malformed rows will be skipped
            </span>
          </>
        ) : null}
      </p>
      {warnings.length ? (
        <Notice tone="warning" title="Worth a look before loading">
          <ul className="grid gap-1">
            {warnings.slice(0, 6).map((w, i) => (
              <li key={`${w.code}-${i}`} className="flex gap-1.5">
                <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                {w.message}
              </li>
            ))}
          </ul>
        </Notice>
      ) : null}
      <div className="grid gap-2">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <p className="text-[13px] font-medium text-ink">Columns</p>
          <p className="text-xs text-ink-2">
            Types inferred from every row · change any that look wrong
          </p>
        </div>
        <div className="overflow-x-auto rounded-sm border border-line">
          <Table>
            <THead>
              <tr>
                <TH>Column</TH>
                <TH>Type</TH>
                <TH>Sample values</TH>
              </tr>
            </THead>
            <tbody>
              {review.columns.map((col) => (
                <TR key={col.name}>
                  <TD>
                    <span className="font-mono text-[12.5px] text-ink">{col.name}</span>
                    {col.display_name !== col.name ? (
                      <p className="text-2xs text-ink-2">from “{col.display_name}”</p>
                    ) : null}
                  </TD>
                  <TD className="w-40">
                    <Select
                      size="sm"
                      aria-label={`Type for ${col.name}`}
                      className="w-full"
                      value={types[col.name]}
                      disabled={disabled}
                      onChange={(e) => onType(col.name, e.target.value as ColumnType)}
                    >
                      {COLUMN_TYPES.map((t) => (
                        <option key={t} value={t}>
                          {t}
                        </option>
                      ))}
                    </Select>
                    {types[col.name] !== col.inferred_type ? (
                      <p className="mt-1 text-2xs text-ink-2">suggested: {col.inferred_type}</p>
                    ) : null}
                  </TD>
                  <TD className="max-w-56 truncate text-ink-2">
                    {col.sample_values.join(", ") || "—"}
                    {col.missing_count > 0 ? (
                      <Badge className="ml-2">{formatInteger(col.missing_count)} empty</Badge>
                    ) : null}
                  </TD>
                </TR>
              ))}
            </tbody>
          </Table>
        </div>
      </div>
    </>
  );
}
