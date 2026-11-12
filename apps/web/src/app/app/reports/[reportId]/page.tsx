import { ArrowLeft } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ResultTableView } from "@/components/data/result-table";
import { PageContainer } from "@/components/shell/app-shell";
import { Badge } from "@/components/ui/badge";
import { SqlCode } from "@/features/analyst/sql-viewer";
import { InsightList } from "@/features/analyst/insights";
import { ReportActions, ReportChart } from "@/features/reports/report-actions";
import { getDataset, getReport, listReports } from "@/lib/data";
import { formatDate } from "@/lib/format";

export function generateStaticParams() {
  return listReports().map((r) => ({ reportId: r.id }));
}

export async function generateMetadata({
  params,
}: PageProps<"/app/reports/[reportId]">): Promise<Metadata> {
  const { reportId } = await params;
  return { title: getReport(reportId)?.title ?? "Report" };
}

export default async function ReportPage({ params }: PageProps<"/app/reports/[reportId]">) {
  const { reportId } = await params;
  const report = getReport(reportId);
  if (!report) notFound();
  const datasetName = getDataset(report.datasetId)?.name ?? report.datasetId;

  return (
    <PageContainer className="max-w-[880px]">
      <div className="flex items-center justify-between gap-3" data-print-hide>
        <Link
          href="/app/reports"
          className="inline-flex items-center gap-1.5 text-[13px] text-ink-2 hover:text-ink"
        >
          <ArrowLeft className="size-3.5" aria-hidden /> All reports
        </Link>
        <ReportActions report={report} datasetName={datasetName} />
      </div>

      <article className="mt-10">
        <header className="border-b border-line pb-8">
          <p className="eyebrow">Report · {datasetName}</p>
          <h1 className="mt-4 text-display text-[36px] text-navy sm:text-[44px]">{report.title}</h1>
          <p className="mt-5 text-[13px] text-ink-2">
            {report.author} · {formatDate(report.createdAt)} · dataset version{" "}
            {report.datasetVersion} · from run <code className="text-ink">{report.runId}</code>
          </p>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {report.tags.map((t) => (
              <Badge key={t}>{t}</Badge>
            ))}
          </div>
        </header>

        <section aria-labelledby="summary" className="py-8">
          <h2 id="summary" className="sr-only">
            Summary
          </h2>
          <p className="[font-family:var(--font-serif)] text-[19px] leading-8 text-ink">
            {report.summary}
          </p>
          <p className="mt-4 text-sm text-ink-2">
            <span className="font-medium text-ink">Question asked:</span> {report.question}
          </p>
        </section>

        {report.sections.map((section) => (
          <section
            key={section.heading}
            aria-labelledby={`sec-${section.heading}`}
            className="border-t border-line py-8"
          >
            <h2 id={`sec-${section.heading}`} className="text-title text-[22px] text-ink">
              {section.heading}
            </h2>
            <p className="mt-2 text-sm text-ink-2">{section.body}</p>
            {section.chart ? (
              <figure className="mt-6 overflow-hidden rounded-md border border-line bg-paper">
                <div className="px-3 pt-5 pb-2">
                  <ReportChart spec={section.chart.spec} table={section.chart.table} height={280} />
                </div>
                <figcaption className="border-t border-line px-4 py-2 text-xs text-ink-2">
                  {section.chart.spec.title}
                  {section.chart.spec.subtitle ? ` · ${section.chart.spec.subtitle}` : ""}
                </figcaption>
                <div className="border-t border-line">
                  <ResultTableView
                    table={section.chart.table}
                    fileName={report.id}
                    maxHeight={9999}
                  />
                </div>
              </figure>
            ) : null}
          </section>
        ))}

        <section aria-labelledby="findings" className="border-t border-line py-8">
          <h2 id="findings" className="mb-5 text-title text-[22px] text-ink">
            Key findings
          </h2>
          <InsightList insights={report.insights} />
        </section>

        {report.limitations.length > 0 ? (
          <section aria-labelledby="limits" className="border-t border-line py-8">
            <h2 id="limits" className="text-title text-[22px] text-ink">
              Limitations & assumptions
            </h2>
            <ul className="mt-4 grid gap-2 text-sm leading-6 text-ink-2">
              {report.limitations.map((l) => (
                <li key={l} className="flex gap-2.5">
                  <span aria-hidden className="mt-2.5 size-1 shrink-0 rounded-full bg-ink-3" />
                  {l}
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {report.methodology.map((m) => (
          <section key={m.sql} aria-labelledby="method" className="border-t border-line py-8">
            <h2 id="method" className="text-title text-[22px] text-ink">
              Methodology
            </h2>
            <p className="mt-2 text-sm leading-6 text-ink-2">{m.step}</p>
            <div className="mt-4 overflow-hidden rounded-sm border border-line">
              <SqlCode sql={m.sql} />
            </div>
          </section>
        ))}
      </article>
    </PageContainer>
  );
}
