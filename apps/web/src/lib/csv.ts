import type { ResultTable } from "@/types/domain";

/** Cells that spreadsheets would interpret as formulas get a leading apostrophe (docs/security/SECURITY.md). */
export function escapeCsvCell(value: string | number): string {
  let text = String(value);
  if (/^[=+\-@\t\r]/.test(text) && typeof value !== "number") text = `'${text}`;
  if (/[",\n\r]/.test(text)) text = `"${text.replace(/"/g, '""')}"`;
  return text;
}

export function tableToCsv(table: ResultTable): string {
  const header = table.columns.map((c) => escapeCsvCell(c.name)).join(",");
  const lines = table.rows.map((row) =>
    table.columns.map((c) => escapeCsvCell(row[c.name] ?? "")).join(","),
  );
  return [header, ...lines].join("\r\n");
}
