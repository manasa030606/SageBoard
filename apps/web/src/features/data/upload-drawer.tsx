"use client";

import { FileUp, UploadCloud } from "lucide-react";
import { useRef, useState, type DragEvent } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Drawer } from "@/components/ui/drawer";
import { Field, Input, Select } from "@/components/ui/field";
import { Notice } from "@/components/ui/states";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/cn";
import { previewCsv, validateUpload, type CsvPreview } from "@/lib/csv-preview";
import { formatBytes } from "@/lib/format";
import type { ColumnType } from "@/types/domain";

const TYPES: ColumnType[] = [
  "integer",
  "bigint",
  "numeric",
  "boolean",
  "date",
  "timestamptz",
  "text",
];

type Step =
  | { kind: "select"; error?: string }
  | { kind: "reading"; file: File }
  | { kind: "review"; file: File; preview: CsvPreview | null; types: ColumnType[] };

export function UploadDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [step, setStep] = useState<Step>({ kind: "select" });
  const [name, setName] = useState("");
  const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const { notify } = useToast();

  function reset() {
    setStep({ kind: "select" });
    setName("");
  }

  async function accept(file: File) {
    const error = validateUpload(file);
    if (error) {
      setStep({ kind: "select", error });
      return;
    }
    setName(file.name.replace(/\.(csv|xlsx)$/i, "").replace(/[_-]+/g, " "));
    setStep({ kind: "reading", file });
    if (file.name.toLowerCase().endsWith(".xlsx")) {
      // Spreadsheet parsing happens server-side; the review step lists sheets later.
      setStep({ kind: "review", file, preview: null, types: [] });
      return;
    }
    try {
      const text = await file.slice(0, 512 * 1024).text();
      const preview = previewCsv(text);
      setStep({
        kind: "review",
        file,
        preview,
        types: preview.columns.map((c) => c.suggestedType),
      });
    } catch (e) {
      setStep({
        kind: "select",
        error: e instanceof Error ? e.message : "The file could not be read.",
      });
    }
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    const file = event.dataTransfer.files[0];
    if (file) void accept(file);
  }

  function finalize() {
    notify({
      tone: "info",
      title: "Upload reviewed",
      description:
        "Loading into a dataset needs the ingestion service (a later phase). Nothing was stored.",
    });
    reset();
    onClose();
  }

  return (
    <Drawer
      open={open}
      onClose={() => {
        reset();
        onClose();
      }}
      title="Upload a dataset"
      description="CSV or Excel, up to 25 MB. You’ll review column types before anything is loaded."
      widthClassName="w-[min(640px,100vw)]"
      footer={
        step.kind === "review" ? (
          <div className="flex items-center justify-between gap-3">
            <Button variant="ghost" onClick={reset}>
              Choose another file
            </Button>
            <Button variant="primary" onClick={finalize} disabled={!name.trim()}>
              Load dataset
            </Button>
          </div>
        ) : null
      }
    >
      <div className="grid gap-5 px-5 py-5">
        {step.kind === "select" ? (
          <>
            {step.error ? (
              <Notice tone="error" title="That file can’t be used">
                {step.error}
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
              <p className="mt-3 text-sm font-medium text-ink">Drag a file here</p>
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
                accept=".csv,.xlsx"
                className="sr-only"
                aria-label="Choose a CSV or Excel file"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) void accept(file);
                  e.target.value = "";
                }}
              />
              <p className="mt-5 text-2xs text-ink-2">
                .csv (comma, semicolon or tab) · .xlsx · max 25 MB · 200 columns
              </p>
            </div>
          </>
        ) : null}

        {step.kind === "reading" ? (
          <p role="status" className="text-sm text-ink-2">
            Reading {step.file.name}…
          </p>
        ) : null}

        {step.kind === "review" ? (
          <>
            <div className="flex items-center justify-between gap-3 rounded-sm border border-line bg-warm/50 px-3.5 py-2.5 text-[13px]">
              <span className="truncate font-medium text-ink">{step.file.name}</span>
              <span className="shrink-0 text-ink-2 tabular">{formatBytes(step.file.size)}</span>
            </div>
            <Field label="Dataset name">
              {({ id }) => <Input id={id} value={name} onChange={(e) => setName(e.target.value)} />}
            </Field>
            {step.preview ? (
              <div className="grid gap-2">
                <div className="flex items-baseline justify-between">
                  <p className="text-[13px] font-medium text-ink">Columns</p>
                  <p className="text-xs text-ink-2">
                    Types suggested from the first {step.preview.sampleRowCount} rows · change any
                    that look wrong
                  </p>
                </div>
                <div className="overflow-hidden rounded-sm border border-line">
                  <Table>
                    <THead>
                      <tr>
                        <TH>Column</TH>
                        <TH>Type</TH>
                        <TH>Sample values</TH>
                      </tr>
                    </THead>
                    <tbody>
                      {step.preview.columns.map((col, i) => (
                        <TR key={`${col.name}-${i}`}>
                          <TD className="font-mono text-[12.5px]">{col.name}</TD>
                          <TD className="w-40">
                            <Select
                              size="sm"
                              aria-label={`Type for ${col.name}`}
                              className="w-full"
                              value={step.types[i]}
                              onChange={(e) => {
                                const types = [...step.types];
                                types[i] = e.target.value as ColumnType;
                                setStep({ ...step, types });
                              }}
                            >
                              {TYPES.map((t) => (
                                <option key={t} value={t}>
                                  {t}
                                </option>
                              ))}
                            </Select>
                          </TD>
                          <TD className="max-w-48 truncate text-ink-2">
                            {col.samples.join(", ") || "—"}
                            {col.nullCount > 0 ? (
                              <Badge className="ml-2">{col.nullCount} empty</Badge>
                            ) : null}
                          </TD>
                        </TR>
                      ))}
                    </tbody>
                  </Table>
                </div>
              </div>
            ) : (
              <Notice tone="info" title="Excel workbook">
                Sheets and column types are detected on the server when the file is loaded.
              </Notice>
            )}
          </>
        ) : null}
      </div>
    </Drawer>
  );
}
