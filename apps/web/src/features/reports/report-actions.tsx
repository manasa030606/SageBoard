"use client";

import { Download, Printer } from "lucide-react";

import { Button } from "@/components/ui/button";
import { reportToMarkdown } from "@/lib/report-markdown";
import type { Report } from "@/types/domain";

export function ReportActions({ report, datasetName }: { report: Report; datasetName: string }) {
  function exportMarkdown() {
    const blob = new Blob([reportToMarkdown(report, datasetName)], {
      type: "text/markdown;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${report.id}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }
  return (
    <div className="flex gap-2" data-print-hide>
      <Button
        variant="secondary"
        size="sm"
        onClick={exportMarkdown}
        leadingIcon={<Download className="size-3.5" aria-hidden />}
      >
        Markdown
      </Button>
      <Button
        variant="secondary"
        size="sm"
        onClick={() => window.print()}
        leadingIcon={<Printer className="size-3.5" aria-hidden />}
      >
        Print / PDF
      </Button>
    </div>
  );
}

export { ChartRenderer as ReportChart } from "@/components/charts/chart-renderer";
