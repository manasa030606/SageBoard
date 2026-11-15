"use client";

import { Database, FileText, MessageSquarePlus } from "lucide-react";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Button, ButtonLink } from "@/components/ui/button";
import { PageHeader, Section } from "@/components/ui/layout";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/states";
import { DATASET_STATUS } from "@/features/data/data-sources";
import { SESSION_STATUS } from "@/features/history/analysis-history";
import { datasets, history, reports } from "@/lib/api/endpoints";
import { formatDate, formatInteger, formatRelative } from "@/lib/format";
import { useApi } from "@/lib/use-api";

const RECENT_LIMIT = 5;

/** Where to start: your datasets, the latest analyses and the latest reports. */
export function Dashboard() {
  const datasetList = useApi(() => datasets.list(), []);
  const analyses = useApi(() => history.sessions({}), []);
  const reportList = useApi(() => reports.list(), []);

  return (
    <>
      <PageHeader
        eyebrow="Overview"
        title="Dashboard"
        description="Your datasets and your most recent work."
        actions={
          <ButtonLink href="/app/analyst" variant="primary">
            Ask a question
          </ButtonLink>
        }
      />

      <div className="mt-8 grid gap-8 xl:grid-cols-2">
        <Section
          surface
          id="datasets"
          title="Datasets"
          actions={<SectionLink href="/app/data">Manage</SectionLink>}
        >
          {datasetList.error ? (
            <LoadError error={datasetList.error} onRetry={datasetList.reload} />
          ) : !datasetList.data ? (
            <ListSkeleton />
          ) : datasetList.data.length === 0 ? (
            <EmptyState
              icon={<Database className="size-5" aria-hidden />}
              title="No datasets yet"
              description="Load the sample dataset or upload a CSV file to start asking questions."
              action={
                <ButtonLink href="/app/data" variant="secondary">
                  Add a dataset
                </ButtonLink>
              }
            />
          ) : (
            <ul className="divide-y divide-line">
              {datasetList.data.map((d) => (
                <li key={d.id} className="flex items-center justify-between gap-4 px-4 py-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-ink">{d.name}</p>
                    <p className="text-[13px] text-ink-2">
                      {d.table_count} {d.table_count === 1 ? "table" : "tables"}
                      {d.total_rows !== null ? ` · ${formatInteger(d.total_rows)} rows` : ""}
                    </p>
                  </div>
                  <Badge tone={DATASET_STATUS[d.status].tone} dot>
                    {DATASET_STATUS[d.status].label}
                  </Badge>
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section
          surface
          id="recent-analyses"
          title="Recent analyses"
          actions={<SectionLink href="/app/history">View all</SectionLink>}
        >
          {analyses.error ? (
            <LoadError error={analyses.error} onRetry={analyses.reload} />
          ) : !analyses.data ? (
            <ListSkeleton />
          ) : analyses.data.items.length === 0 ? (
            <EmptyState
              icon={<MessageSquarePlus className="size-5" aria-hidden />}
              title="No analyses yet"
              description="Questions you ask on the Analyst page appear here."
            />
          ) : (
            <ul className="divide-y divide-line">
              {analyses.data.items.slice(0, RECENT_LIMIT).map((a) => (
                <li key={a.id}>
                  <Link
                    href={`/app/analyst?conversation=${a.conversation_id}`}
                    className="flex items-center justify-between gap-4 px-4 py-3 hover:bg-warm/60"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-ink">{a.question}</p>
                      <p className="text-[13px] text-ink-2">
                        {a.dataset_name} · {formatRelative(a.created_at, new Date())}
                      </p>
                    </div>
                    <Badge tone={SESSION_STATUS[a.status].tone}>
                      {SESSION_STATUS[a.status].label}
                    </Badge>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section
          surface
          id="recent-reports"
          title="Recent reports"
          className="xl:col-span-2"
          actions={<SectionLink href="/app/reports">View all</SectionLink>}
        >
          {reportList.error ? (
            <LoadError error={reportList.error} onRetry={reportList.reload} />
          ) : !reportList.data ? (
            <ListSkeleton />
          ) : reportList.data.items.length === 0 ? (
            <EmptyState
              icon={<FileText className="size-5" aria-hidden />}
              title="No reports yet"
              description="Save a finished analysis as a report from the Analyst page."
            />
          ) : (
            <ul className="divide-y divide-line">
              {reportList.data.items.slice(0, RECENT_LIMIT).map((r) => (
                <li key={r.id}>
                  <Link
                    href={`/app/reports/${r.id}`}
                    className="flex items-center justify-between gap-4 px-4 py-3 hover:bg-warm/60"
                  >
                    <p className="truncate text-sm font-medium text-ink">{r.title}</p>
                    <span className="shrink-0 text-[13px] text-ink-2">
                      {formatDate(r.created_at)}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Section>
      </div>
    </>
  );
}

function SectionLink({ href, children }: { href: string; children: string }) {
  return (
    <Link href={href} className="text-[13px] text-forest hover:underline">
      {children}
    </Link>
  );
}

function ListSkeleton() {
  return (
    <div className="grid gap-3 p-4" aria-busy="true">
      <Skeleton className="h-9 w-full" />
      <Skeleton className="h-9 w-full" />
      <Skeleton className="h-9 w-full" />
    </div>
  );
}

function LoadError({
  error,
  onRetry,
}: {
  error: { message: string; code?: string };
  onRetry: () => void;
}) {
  return (
    <ErrorState
      title="Couldn’t load this section"
      description={error.message}
      code={error.code}
      action={
        <Button variant="secondary" onClick={onRetry}>
          Try again
        </Button>
      }
    />
  );
}
