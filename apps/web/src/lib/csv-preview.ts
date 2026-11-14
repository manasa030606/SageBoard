import type { ColumnType } from "@/types/domain";

/*
 * Browser-side preview of an uploaded CSV: parse the header and a sample of rows
 * and suggest column types. This is only a preview for the review step; the
 * authoritative parsing and loading happen server-side (ingestion, later phase).
 */
export const MAX_UPLOAD_BYTES = 25 * 1024 * 1024;
export const ACCEPTED_EXTENSIONS = [".csv"] as const;

export interface PreviewColumn {
  name: string;
  suggestedType: ColumnType;
  nullCount: number;
  samples: string[];
}

export interface CsvPreview {
  delimiter: "," | ";" | "\t";
  columns: PreviewColumn[];
  sampleRowCount: number;
}

export function validateUpload(file: { name: string; size: number }): string | null {
  const lower = file.name.toLowerCase();
  if (lower.endsWith(".xlsx") || lower.endsWith(".xls"))
    return "Excel files aren’t supported yet. In Excel choose File → Save As → “CSV UTF-8”, then upload that file.";
  if (!ACCEPTED_EXTENSIONS.some((ext) => lower.endsWith(ext)))
    return "Only .csv files are supported.";
  if (file.size === 0) return "This file is empty.";
  if (file.size > MAX_UPLOAD_BYTES)
    return `This file is ${(file.size / 1024 / 1024).toFixed(1)} MB. The limit is 25 MB.`;
  return null;
}

/** RFC 4180-style line parser (quotes, escaped quotes, delimiters inside quotes). */
export function parseCsvLine(line: string, delimiter: string): string[] {
  const out: string[] = [];
  let cur = "";
  let quoted = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (quoted) {
      if (ch === '"' && line[i + 1] === '"') {
        cur += '"';
        i++;
      } else if (ch === '"') quoted = false;
      else cur += ch;
    } else if (ch === '"') quoted = true;
    else if (ch === delimiter) {
      out.push(cur);
      cur = "";
    } else cur += ch;
  }
  out.push(cur);
  return out.map((v) => v.trim());
}

function detectDelimiter(header: string): CsvPreview["delimiter"] {
  const counts = {
    ",": header.split(",").length,
    ";": header.split(";").length,
    "\t": header.split("\t").length,
  };
  return (Object.entries(counts).sort((a, b) => b[1] - a[1])[0]?.[0] ??
    ",") as CsvPreview["delimiter"];
}

const NULLS = new Set(["", "na", "n/a", "null", "none", "-"]);

export function inferType(values: string[]): ColumnType {
  const present = values.filter((v) => !NULLS.has(v.toLowerCase()));
  if (present.length === 0) return "text";
  const all = (re: RegExp) => present.every((v) => re.test(v));
  if (all(/^(true|false|yes|no)$/i)) return "boolean";
  if (all(/^-?\d+$/))
    return present.some((v) => Math.abs(Number(v)) > 2_147_483_647) ? "bigint" : "integer";
  if (all(/^-?[$€£₹]?\s?\d{1,3}(,\d{3})*(\.\d+)?$|^-?\d+(\.\d+)?$/)) return "numeric";
  if (all(/^\d{4}-\d{2}-\d{2}$/)) return "date";
  if (all(/^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2})?/)) return "timestamptz";
  return "text";
}

export function previewCsv(text: string, maxRows = 200): CsvPreview {
  const lines = text
    .replace(/^﻿/, "")
    .split(/\r?\n/)
    .filter((l) => l.trim().length > 0);
  const header = lines[0];
  if (!header) throw new Error("The file has no header row.");
  const delimiter = detectDelimiter(header);
  const names = parseCsvLine(header, delimiter);
  if (names.length < 1 || names.every((n) => !n)) throw new Error("The header row is empty.");
  const rows = lines.slice(1, maxRows + 1).map((l) => parseCsvLine(l, delimiter));
  const columns = names.map((name, ci) => {
    const values = rows.map((r) => r[ci] ?? "");
    return {
      name: name || `column_${ci + 1}`,
      suggestedType: inferType(values),
      nullCount: values.filter((v) => NULLS.has(v.toLowerCase())).length,
      samples: values.filter((v) => !NULLS.has(v.toLowerCase())).slice(0, 3),
    };
  });
  return { delimiter, columns, sampleRowCount: rows.length };
}
