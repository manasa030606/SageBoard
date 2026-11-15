"use client";

import { ArrowRight, FileText } from "lucide-react";
import Link from "next/link";

import { ButtonLink, Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/layout";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/states";
import { reports } from "@/lib/api/endpoints";
import { formatDate } from "@/lib/format";
import { useApi } from "@/lib/use-api";

export function ReportsList() {
  const list = useApi(() => reports.list(), []);
  const items = list.data?.items ?? [];

  return (
    <>
      <PageHeader
        eyebrow="Saved work"
        title="Reports"
        description="Write-ups saved from finished analyses. Each keeps a snapshot of the question, summary and the SQL that ran."
      />
      {list.error ? (
        <div className="mt-8 rounded-md border border-line bg-paper">
          <ErrorState
            title="Couldn’t load your reports"
            description={list.error.message}
            code={list.error.code}
            action={
              <Button variant="secondary" onClick={list.reload}>
                Try again
              </Button>
            }
          />
        </div>
      ) : list.loading && !list.data ? (
        <div className="mt-8 grid gap-3" aria-busy="true">
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          className="mt-10 rounded-md border border-dashed border-line-strong"
          icon={<FileText className="size-5" aria-hidden />}
          title="No reports yet"
          description="Reports are saved from finished analyses. Ask a question on the Analyst page, then use “Save as report” on the answer."
          action={
            <ButtonLink href="/app/analyst" variant="secondary">
              See a sample run
            </ButtonLink>
          }
        />
      ) : (
        <ul className="mt-8 divide-y divide-line border-y border-line">
          {items.map((r) => (
            <li key={r.id}>
              <Link
                href={`/app/reports/${r.id}`}
                className="group flex items-center justify-between gap-6 py-6 transition-colors duration-100 hover:bg-paper/70 md:px-3"
              >
                <h2 className="text-title text-[21px] text-ink group-hover:text-forest">
                  {r.title}
                </h2>
                <span className="flex shrink-0 items-center gap-3 text-[13px] text-ink-2">
                  {formatDate(r.created_at)}
                  <ArrowRight
                    className="size-3.5 text-forest opacity-0 transition-opacity group-hover:opacity-100"
                    aria-hidden
                  />
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
