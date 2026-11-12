import { ArrowRight, FileText } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { PageContainer } from "@/components/shell/app-shell";
import { Badge } from "@/components/ui/badge";
import { ButtonLink } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/layout";
import { EmptyState } from "@/components/ui/states";
import { getDataset, listReports } from "@/lib/data";
import { formatDate } from "@/lib/format";

export const metadata: Metadata = { title: "Reports" };

export default function ReportsPage() {
  const reports = listReports();
  return (
    <PageContainer>
      <PageHeader
        eyebrow="Saved work"
        title="Reports"
        description="Write-ups saved from analyses. Each keeps a snapshot of its results, insights and SQL."
        actions={
          <ButtonLink href="/app/analyst" variant="secondary">
            New analysis
          </ButtonLink>
        }
      />

      {reports.length === 0 ? (
        <EmptyState
          className="mt-10 rounded-md border border-dashed border-line-strong"
          icon={<FileText className="size-5" aria-hidden />}
          title="No reports yet"
          description="Run an analysis and choose “Save as report” to keep it here."
          action={
            <ButtonLink href="/app/analyst" variant="primary">
              Open the analyst
            </ButtonLink>
          }
        />
      ) : (
        <ul className="mt-8 divide-y divide-line border-y border-line">
          {reports.map((r) => (
            <li key={r.id}>
              <Link
                href={`/app/reports/${r.id}`}
                className="group grid gap-x-10 gap-y-2 py-6 transition-colors duration-100 hover:bg-paper/70 md:grid-cols-[minmax(0,1fr)_200px] md:px-3"
              >
                <div className="min-w-0">
                  <h2 className="text-title text-[21px] text-ink group-hover:text-forest">
                    {r.title}
                  </h2>
                  <p className="mt-2 line-clamp-2 max-w-3xl text-sm leading-6 text-ink-2">
                    {r.summary}
                  </p>
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {r.tags.map((t) => (
                      <Badge key={t}>{t}</Badge>
                    ))}
                  </div>
                </div>
                <dl className="grid content-start gap-1 text-[13px] text-ink-2 md:text-right">
                  <dt className="sr-only">Created</dt>
                  <dd className="text-ink">{formatDate(r.createdAt)}</dd>
                  <dt className="sr-only">Dataset</dt>
                  <dd>{getDataset(r.datasetId)?.name}</dd>
                  <dt className="sr-only">Contents</dt>
                  <dd>
                    {r.insights.length} findings · {r.author}
                  </dd>
                  <dd
                    aria-hidden
                    className="mt-2 hidden items-center justify-end gap-1 text-forest opacity-0 transition-opacity group-hover:opacity-100 md:flex"
                  >
                    Read <ArrowRight className="size-3.5" />
                  </dd>
                </dl>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </PageContainer>
  );
}
