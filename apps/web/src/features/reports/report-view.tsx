"use client";

import { ArrowLeft, Download, FileText, Printer, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { ChartRenderer } from "@/components/charts/chart-renderer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ErrorState, Notice, Skeleton } from "@/components/ui/states";
import { useToast } from "@/components/ui/toast";
import { toResultTable } from "@/features/analyst/live/adapt";
import { SqlCode } from "@/features/analyst/sql-viewer";
import type { ChartSpec } from "@/types/domain";
import { reports } from "@/lib/api/endpoints";
import type { ReportChart, ReportDetail } from "@/lib/api/types";
import { fileSlug, saveFile } from "@/lib/download";
import { formatDate, formatInteger } from "@/lib/format";
import { errorMessage, useApi } from "@/lib/use-api";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-b border-line py-8 last:border-0">
      <h2 className="eyebrow">{title}</h2>
      <div className="mt-4">{children}</div>
    </section>
  );
}

function List({ items }: { items: string[] }) {
  return (
    <ul className="grid max-w-prose list-disc gap-1.5 pl-5 text-[14px] leading-6 text-ink">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

function SavedChart({ chart }: { chart: ReportChart }) {
  const table = useMemo(
    () =>
      chart.data.length && chart.columns.length
        ? toResultTable(
            chart.columns.map((name) => ({ name, type: "text" })),
            chart.data,
          )
        : null,
    [chart],
  );
  return (
    <figure className="rounded-sm border border-line p-4">
      <figcaption className="mb-3">
        <p className="text-[14px] font-medium text-ink">{chart.title ?? "Chart"}</p>
        {chart.subtitle ? <p className="text-[12.5px] text-ink-2">{chart.subtitle}</p> : null}
      </figcaption>
      {table ? (
        <ChartRenderer
          spec={{
            chartType: chart.chart_type as ChartSpec["chartType"],
            title: chart.title ?? "Chart",
            subtitle: chart.subtitle ?? undefined,
            x: chart.x ?? "",
            y: chart.y,
            valueFormat: chart.value_format,
          }}
          table={table}
          height={240}
        />
      ) : (
        <p className="text-[13px] text-ink-2">No data was stored for this chart.</p>
      )}
    </figure>
  );
}

function ReportBody({ data }: { data: ReportDetail }) {
  const c = data.content;
  const method = c.methodology;
  const steps = c.steps?.filter((s) => s.sql) ?? [];
  const meta = [
    method?.intent ? `Intent: ${method.intent}` : null,
    method?.time_range ? `Time range: ${method.time_range}` : null,
    method?.metrics.length ? `Metrics: ${method.metrics.join(", ")}` : null,
    method?.dimensions.length ? `Dimensions: ${method.dimensions.join(", ")}` : null,
    method?.filters.length ? `Filters: ${method.filters.join(", ")}` : null,
  ].filter((x): x is string => x !== null);

  return (
    <article className="mt-10">
      <header className="border-b border-line pb-8">
        <p className="eyebrow">Report{c.dataset?.name ? ` · ${c.dataset.name}` : ""}</p>
        <h1 className="mt-4 text-display text-[36px] text-navy sm:text-[44px]">{data.title}</h1>
        <p className="mt-5 text-[13px] text-ink-2">
          Saved {formatDate(data.created_at)}
          {c.dataset ? ` · dataset version ${c.dataset.version}` : ""}
        </p>
      </header>

      {c.question ? (
        <Section title="Question">
          <p className="text-[17px] leading-7 text-ink">{c.question}</p>
          {method?.restated_question && method.restated_question !== c.question ? (
            <p className="mt-2 text-[13px] text-ink-2">
              Interpreted as: {method.restated_question}
            </p>
          ) : null}
        </Section>
      ) : null}

      {c.dataset?.tables?.length ? (
        <Section title="Dataset">
          {c.dataset.description ? (
            <p className="mb-3 max-w-prose text-[14px] text-ink-2">{c.dataset.description}</p>
          ) : null}
          <ul className="flex flex-wrap gap-2">
            {c.dataset.tables.map((t) => (
              <li key={t.name}>
                <Badge tone="neutral">
                  {t.name} · {formatInteger(t.rows)} rows
                </Badge>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}

      <Section title="Executive summary">
        {data.summary_edited_by_user ? (
          <p className="mb-2 text-[12.5px] text-ink-2">Edited after the analysis ran.</p>
        ) : null}
        <p className="max-w-prose text-[15px] leading-7 whitespace-pre-line text-ink">
          {data.summary || "No summary was recorded for this analysis."}
        </p>
        {data.fidelity?.status === "flagged" ? (
          <Notice tone="warning" title="Numbers not found in the stored results" className="mt-4">
            <ul className="mt-1 grid gap-1">
              {data.fidelity.issues.map((issue) => (
                <li key={issue.where}>
                  {issue.where}: <span className="tabular">{issue.numbers.join(", ")}</span>
                </li>
              ))}
            </ul>
          </Notice>
        ) : null}
      </Section>

      {method ? (
        <Section title="Analysis methodology">
          {meta.length ? <List items={meta} /> : null}
          {method.plan_steps.length ? (
            <>
              <h3 className="mt-5 mb-2 text-[13px] font-medium text-ink">Plan</h3>
              <List items={method.plan_steps.map((s) => `${s.step_id}: ${s.purpose}`)} />
            </>
          ) : null}
          {method.analysis_tasks.length ? (
            <>
              <h3 className="mt-5 mb-2 text-[13px] font-medium text-ink">
                Calculations performed on the results
              </h3>
              <List items={method.analysis_tasks} />
            </>
          ) : null}
          {method.verification ? (
            <p className="mt-4 text-[12.5px] text-ink-2">
              {method.verification.verified_insights} insights verified,{" "}
              {method.verification.rejected_insights} rejected.
            </p>
          ) : null}
        </Section>
      ) : null}

      {steps.length || c.queries?.length ? (
        <Section title="SQL queries">
          <div className="grid gap-4">
            {(steps.length
              ? steps.map((s) => ({
                  key: s.step_id,
                  label: `${s.step_id}${s.purpose ? `: ${s.purpose}` : ""}`,
                  sql: s.sql ?? "",
                  rows: s.row_count,
                  truncated: s.truncated,
                }))
              : (c.queries ?? []).map((q, i) => ({
                  key: String(i),
                  label: `Query ${i + 1}`,
                  sql: q.sql,
                  rows: q.row_count,
                  truncated: q.truncated,
                }))
            ).map((q) => (
              <div key={q.key}>
                <p className="mb-1.5 text-[13px] text-ink-2">
                  {q.label}
                  {q.rows != null
                    ? ` · ${formatInteger(q.rows)} rows${q.truncated ? "+" : ""}`
                    : ""}
                </p>
                <div className="overflow-hidden rounded-sm border border-line">
                  <SqlCode sql={q.sql} />
                </div>
              </div>
            ))}
          </div>
        </Section>
      ) : null}

      {c.version && c.version >= 2 ? (
        <>
          <Section title="Key findings">
            {c.findings?.length ? (
              <ul className="grid gap-4">
                {c.findings.map((f) => (
                  <li key={f.headline} className="max-w-prose">
                    <p className="text-[15px] font-medium text-ink">{f.headline}</p>
                    <p className="mt-1 text-[14px] leading-6 text-ink-2">{f.detail}</p>
                    <p className="mt-1.5 flex gap-2">
                      <Badge tone="neutral">{f.category}</Badge>
                      <Badge tone={f.verification === "verified" ? "positive" : "warning"}>
                        {f.verification}
                      </Badge>
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-[13px] text-ink-2">
                No verified findings were stored for this analysis.
              </p>
            )}
          </Section>

          <Section title="Visualizations">
            {c.charts?.length ? (
              <div className="grid gap-4 md:grid-cols-2">
                {c.charts.map((chart, i) => (
                  <SavedChart key={`${chart.step_id}-${i}`} chart={chart} />
                ))}
              </div>
            ) : (
              <p className="text-[13px] text-ink-2">This analysis produced no charts.</p>
            )}
          </Section>

          <Section title="Business recommendations">
            {c.recommendations?.length ? (
              <ul className="grid gap-4">
                {c.recommendations.map((r) => (
                  <li key={r.headline} className="max-w-prose">
                    <p className="text-[15px] font-medium text-ink">{r.headline}</p>
                    <p className="mt-1 text-[14px] leading-6 text-ink-2">{r.detail}</p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-[13px] text-ink-2">
                The analysis did not support any recommendation strongly enough to state one.
              </p>
            )}
          </Section>

          <Section title="Limitations">
            <List
              items={
                c.limitations?.length ? c.limitations : ["No specific limitations were recorded."]
              }
            />
            <p className="mt-4 text-[12.5px] text-ink-2">
              {data.fidelity?.status === "verified"
                ? "Every number in this report was matched against the stored query results."
                : data.fidelity?.status === "flagged"
                  ? "Some numbers could not be matched against the stored results (see the notice under the summary)."
                  : "Numeric verification was not available for this report."}
            </p>
          </Section>
        </>
      ) : (
        <Section title="Note">
          <p className="text-[13px] text-ink-2">
            This report was saved before findings, charts and limitations were stored with it. The
            PDF contains what was saved.
          </p>
        </Section>
      )}
    </article>
  );
}

export function ReportView() {
  const { reportId } = useParams<{ reportId: string }>();
  const router = useRouter();
  const report = useApi(() => reports.get(reportId), [reportId]);
  const [busy, setBusy] = useState<null | "pdf" | "md" | "delete">(null);
  const { notify } = useToast();
  const data = report.data;

  async function exportAs(kind: "pdf" | "md") {
    if (!data) return;
    setBusy(kind);
    try {
      if (kind === "pdf") {
        saveFile(fileSlug(data.title, "pdf"), await reports.pdf(data.id));
      } else {
        saveFile(fileSlug(data.title, "md"), await reports.markdown(data.id), "text/markdown");
      }
    } catch (error) {
      notify({ tone: "error", title: "Export failed", description: errorMessage(error) });
    } finally {
      setBusy(null);
    }
  }

  async function remove() {
    if (!data) return;
    setBusy("delete");
    try {
      await reports.remove(data.id);
      router.replace("/app/reports");
    } catch (error) {
      notify({
        tone: "error",
        title: "Couldn’t delete the report",
        description: errorMessage(error),
      });
      setBusy(null);
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
              size="sm"
              onClick={() => void exportAs("pdf")}
              disabled={busy !== null}
              leadingIcon={<FileText className="size-3.5" aria-hidden />}
            >
              {busy === "pdf" ? "Preparing PDF…" : "Download PDF"}
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => void exportAs("md")}
              disabled={busy !== null}
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
              Print
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => void remove()}
              disabled={busy !== null}
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
        <ReportBody data={data} />
      )}
    </>
  );
}
