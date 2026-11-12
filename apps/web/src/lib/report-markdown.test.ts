import { describe, expect, it } from "vitest";

import { REPORTS } from "@/mocks/workspace";

import { reportToMarkdown, tableToMarkdown } from "./report-markdown";

describe("reportToMarkdown", () => {
  it("includes title, every insight headline, the data table and the SQL", () => {
    const report = REPORTS[0]!;
    const md = reportToMarkdown(report, "Retail demo");
    expect(md.startsWith(`# ${report.title}`)).toBe(true);
    for (const i of report.insights) expect(md).toContain(i.headline);
    expect(md).toContain("```sql");
    expect(md).toContain("| Region |");
  });

  it("right-aligns numeric columns and escapes pipes in text", () => {
    const md = tableToMarkdown({
      columns: [
        { name: "a", label: "A", format: "text" },
        { name: "b", label: "B", format: "currency" },
      ],
      rows: [{ a: "x|y", b: 1200 }],
      rowCount: 1,
      truncated: false,
    });
    expect(md).toContain("| --- | ---: |");
    expect(md).toContain("x\\|y");
    expect(md).toContain("$1,200");
  });
});
