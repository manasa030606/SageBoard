import { formatMonth, formatValue } from "@/lib/format";
import type { Report, ResultTable } from "@/types/domain";

function cell(
  value: string | number | undefined,
  format: ResultTable["columns"][number]["format"],
): string {
  if (value === undefined) return "";
  if (format === "text") return String(value).replace(/\|/g, "\\|");
  if (format === "month") return formatMonth(String(value), { withYear: true });
  return formatValue(Number(value), format);
}

export function tableToMarkdown(table: ResultTable): string {
  const head = `| ${table.columns.map((c) => c.label).join(" | ")} |`;
  const rule = `| ${table.columns.map((c) => (c.format === "text" || c.format === "month" ? "---" : "---:")).join(" | ")} |`;
  const rows = table.rows.map(
    (r) => `| ${table.columns.map((c) => cell(r[c.name], c.format)).join(" | ")} |`,
  );
  return [head, rule, ...rows].join("\n");
}

/** Markdown export of a report (API_SPECIFICATION §7 `export.md`, generated client-side for now). */
export function reportToMarkdown(report: Report, datasetName: string): string {
  const out: string[] = [
    `# ${report.title}`,
    "",
    `_Question:_ ${report.question}  `,
    `_Dataset:_ ${datasetName} (version ${report.datasetVersion}) · _Author:_ ${report.author} · _Created:_ ${report.createdAt.slice(0, 10)}`,
    "",
    "## Summary",
    "",
    report.summary,
    "",
    "## Key findings",
    "",
    ...report.insights.map((i, n) => `${n + 1}. **${i.headline}** ${i.detail}`),
    "",
  ];
  for (const section of report.sections) {
    out.push(`## ${section.heading}`, "", section.body, "");
    if (section.chart) out.push(tableToMarkdown(section.chart.table), "");
  }
  if (report.limitations.length)
    out.push("## Limitations", "", ...report.limitations.map((l) => `- ${l}`), "");
  if (report.methodology.length) {
    out.push("## Methodology", "");
    for (const m of report.methodology) out.push(m.step, "", "```sql", m.sql, "```", "");
  }
  return out.join("\n");
}
