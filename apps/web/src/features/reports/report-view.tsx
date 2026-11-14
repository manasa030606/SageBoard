"use client";

import { ArrowLeft, Download, Printer, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { ErrorState, Skeleton } from "@/components/ui/states";
import { useToast } from "@/components/ui/toast";
import { SqlCode } from "@/features/analyst/sql-viewer";
import { reports } from "@/lib/api/endpoints";
import { formatDate, formatInteger } from "@/lib/format";
import { errorMessage, useApi } from "@/lib/use-api";

function download(filename: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/markdown;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function ReportView() {
  const { reportId } = useParams<{ reportId: string }>();
  const router = useRouter();
  const report = useApi(() => reports.get(reportId), [reportId]);
  const [busy, setBusy] = useState(false);
  const { notify } = useToast();
  const data = report.data;

  async function exportMarkdown() {
    if (!data) return;
    try {
      const text = await reports.markdown(data.id);
      download(
        `${
          data.title
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, "-")
            .replace(/^-|-$/g, "") || "report"
        }.md`,
        text,
      );
    } catch (error) {
      notify({ tone: "error", title: "Export failed", description: errorMessage(error) });
    }
  }

  async function remove() {
    if (!data) return;
    setBusy(true);
    try {
      await reports.remove(data.id);
      router.replace("/app/reports");
    } catch (error) {
      notify({
        tone: "error",
        title: "Couldn’t delete the report",
        description: errorMessage(error),
      });
      setBusy(false);
    }
  }

  return (
    <>
      <div className="flex items-center justify-between gap-3" data-print-hide>
        <Link
          href="/app/reports"
          className="inline-flex items-center gap-1.5 text-[13px] text-ink-2 hover:text-ink"
        >
          <ArrowLeft className="size-3.5" aria-hidden /> All reports
        </Link>
        {data ? (
          <div className="flex gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => void exportMarkdown()}
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
            <Button
              variant="ghost"
              size="sm"
              onClick={() => void remove()}
              disabled={busy}
              leadingIcon={<Trash2 className="size-3.5" aria-hidden />}
            >
              Delete
            </Button>
          </div>
        ) : null}
      </div>

      {report.error ? (
        <ErrorState
          title={report.error.status === 404 ? "Report not found" : "Couldn’t load the report"}
          description={
            report.error.status === 404 ? "It may have been deleted." : report.error.message
          }
          code={report.error.code}
        />
      ) : !data ? (
        <div className="mt-10 grid gap-4" aria-busy="true">
          <Skeleton className="h-10 w-3/4" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : (
        <article className="mt-10">
          <header className="border-b border-line pb-8">
            <p className="eyebrow">
              Report{data.content.dataset?.name ? ` · ${data.content.dataset.name}` : ""}
            </p>
            <h1 className="mt-4 text-display text-[36px] text-navy sm:text-[44px]">{data.title}</h1>
            <p className="mt-5 text-[13px] text-ink-2">
              Saved {formatDate(data.created_at)}
              {data.content.dataset ? ` · dataset version ${data.content.dataset.version}` : ""}
            </p>
          </header>
          {data.content.question ? (
            <section className="border-b border-line py-8">
              <h2 className="eyebrow">Question</h2>
              <p className="mt-3 text-[17px] leading-7 text-ink">{data.content.question}</p>
            </section>
          ) : null}
          <section className="border-b border-line py-8">
            <h2 className="eyebrow">Summary</h2>
            <p className="mt-3 max-w-prose text-[15px] leading-7 whitespace-pre-line text-ink">
              {data.summary || "No summary was recorded for this analysis."}
            </p>
          </section>
          {data.content.queries?.length ? (
            <section className="py-8">
              <h2 className="eyebrow">Methodology</h2>
              <div className="mt-4 grid gap-4">
                {data.content.queries.map((q, i) => (
                  <div key={i}>
                    <p className="mb-1.5 text-[13px] text-ink-2">
                      Query {i + 1}
                      {q.row_count != null
                        ? ` · ${formatInteger(q.row_count)} rows${q.truncated ? "+" : ""}`
                        : ""}
                    </p>
                    <div className="overflow-hidden rounded-sm border border-line">
                      <SqlCode sql={q.sql} />
                    </div>
                  </div>
                ))}
              </div>
            </section>
          ) : null}
        </article>
      )}
    </>
  );
}
