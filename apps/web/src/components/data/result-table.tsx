"use client";

import { ArrowDown, ArrowUp, ArrowUpDown, Download } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { cn } from "@/lib/cn";
import { tableToCsv } from "@/lib/csv";
import { formatMonth, formatValue } from "@/lib/format";
import type { ResultColumn, ResultTable } from "@/types/domain";

function renderCell(value: string | number | undefined, column: ResultColumn) {
  if (value === undefined || value === null || value === "")
    return <span className="text-ink-3">—</span>;
  if (column.format === "text") return String(value);
  if (column.format === "month") return formatMonth(String(value), { withYear: true });
  const n = Number(value);
  if (column.format === "percent") {
    return (
      <span className={cn(n > 0 && "text-forest", n < 0 && "text-rust")}>
        {n > 0 ? "+" : ""}
        {formatValue(n, "percent")}
      </span>
    );
  }
  return formatValue(n, column.format);
}

const isNumeric = (c: ResultColumn) => c.format !== "text" && c.format !== "month";

export function ResultTableView({
  table,
  highlightRows = [],
  fileName = "result",
  maxHeight = 420,
}: {
  table: ResultTable;
  highlightRows?: number[];
  fileName?: string;
  maxHeight?: number;
}) {
  const [sort, setSort] = useState<{ key: string; dir: "asc" | "desc" } | null>(null);

  // Keep original indices so evidence highlighting survives sorting.
  const rows = useMemo(() => {
    const indexed = table.rows.map((row, index) => ({ row, index }));
    if (!sort) return indexed;
    return [...indexed].sort((a, b) => {
      const av = a.row[sort.key];
      const bv = b.row[sort.key];
      const cmp =
        typeof av === "number" && typeof bv === "number"
          ? av - bv
          : String(av).localeCompare(String(bv));
      return sort.dir === "asc" ? cmp : -cmp;
    });
  }, [table.rows, sort]);

  function toggle(key: string) {
    setSort((current) =>
      current?.key !== key
        ? { key, dir: "desc" }
        : current.dir === "desc"
          ? { key, dir: "asc" }
          : null,
    );
  }

  function download() {
    const blob = new Blob([tableToCsv(table)], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${fileName}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div>
      <div className="overflow-auto" style={{ maxHeight }}>
        <Table>
          <THead className="sticky top-0 z-[1] bg-warm">
            <tr>
              {table.columns.map((column) => {
                const active = sort?.key === column.name;
                const Icon = !active ? ArrowUpDown : sort.dir === "asc" ? ArrowUp : ArrowDown;
                return (
                  <TH
                    key={column.name}
                    align={isNumeric(column) ? "right" : "left"}
                    aria-sort={active ? (sort.dir === "asc" ? "ascending" : "descending") : "none"}
                    className="px-0"
                  >
                    <button
                      type="button"
                      onClick={() => toggle(column.name)}
                      className={cn(
                        "inline-flex h-9 w-full items-center gap-1 px-4 uppercase hover:text-ink",
                        isNumeric(column) && "justify-end",
                        active && "text-ink",
                      )}
                    >
                      {column.label}
                      <Icon className={cn("size-3", !active && "opacity-40")} aria-hidden />
                    </button>
                  </TH>
                );
              })}
            </tr>
          </THead>
          <tbody>
            {rows.map(({ row, index }) => {
              const highlighted = highlightRows.includes(index);
              return (
                <TR
                  key={index}
                  className={cn(highlighted && "bg-amber-100/70")}
                  data-highlighted={highlighted || undefined}
                >
                  {table.columns.map((column, ci) => (
                    <TD
                      key={column.name}
                      numeric={isNumeric(column)}
                      className={cn(
                        ci === 0 && "font-medium",
                        highlighted && ci === 0 && "shadow-[inset_2px_0_0_var(--color-amber)]",
                      )}
                    >
                      {renderCell(row[column.name], column)}
                    </TD>
                  ))}
                </TR>
              );
            })}
          </tbody>
        </Table>
      </div>
      <div className="flex items-center justify-between gap-3 border-t border-line px-4 py-2 text-xs text-ink-2">
        <span className="tabular">
          {table.rowCount.toLocaleString("en-US")} {table.rowCount === 1 ? "row" : "rows"}
          {table.truncated ? " · truncated at the row limit" : ""}
        </span>
        <Button
          size="sm"
          variant="ghost"
          onClick={download}
          leadingIcon={<Download className="size-3.5" aria-hidden />}
        >
          Export CSV
        </Button>
      </div>
    </div>
  );
}
