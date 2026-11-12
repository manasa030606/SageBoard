import { Check, CornerDownRight, Database, RotateCcw } from "lucide-react";

import { getScenario } from "@/lib/data";
import { formatCurrency, formatPercent } from "@/lib/format";

/**
 * A live-rendered (not screenshot) preview of a completed run, built from the
 * recorded regional-growth sample so its numbers match the product.
 */
export function ProductPreview() {
  const scenario = getScenario("sc_regions");
  if (!scenario) return null;
  const { result } = scenario;
  const rows = result.table?.rows.slice(0, 4) ?? [];
  const insight = result.insights[0];
  const shownSteps = result.timeline.filter((t) =>
    ["retrieve_schema", "validate_sql", "execute_sql", "verify_insights"].includes(t.node),
  );

  return (
    <div className="overflow-hidden rounded-md border border-line bg-paper shadow-[0_1px_0_var(--color-line),0_24px_48px_-32px_rgb(25_44_53/0.35)]">
      <span className="sr-only">
        Preview of the Sageboard analyst answering a question about regional revenue growth.
      </span>
      <div aria-hidden>
        <div className="flex items-center justify-between border-b border-line bg-warm/60 px-4 py-2.5">
          <span className="flex items-center gap-2 text-xs text-ink-2">
            <Database className="size-3.5" /> Retail demo
          </span>
          <span className="eyebrow">Sample run</span>
        </div>

        <div className="grid gap-5 p-5 md:grid-cols-[1fr_200px]">
          <div className="min-w-0">
            <p className="text-[15px] leading-6 font-medium text-ink">{scenario.question}</p>

            <div className="mt-4 overflow-hidden rounded-sm border border-line">
              <table className="w-full text-[12px]">
                <thead className="bg-warm/70 text-2xs tracking-[0.06em] text-ink-2 uppercase">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium">Region</th>
                    <th className="px-3 py-2 text-right font-medium">Q3 2026</th>
                    <th className="px-3 py-2 text-right font-medium">Growth</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, i) => (
                    <tr
                      key={String(row.region)}
                      className={i < 2 ? "bg-amber-100/60" : "border-t border-line/70"}
                    >
                      <td className="px-3 py-1.5 text-ink">{String(row.region)}</td>
                      <td className="px-3 py-1.5 text-right font-mono tabular">
                        {formatCurrency(Number(row.q3_revenue))}
                      </td>
                      <td
                        className={`px-3 py-1.5 text-right font-mono tabular ${Number(row.growth) < 0 ? "text-rust" : "text-forest"}`}
                      >
                        {formatPercent(Number(row.growth), { signed: true })}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {insight ? (
              <div className="mt-4 border-l-2 border-forest pl-3">
                <p className="text-[13px] font-medium text-ink">{insight.headline}</p>
                <p className="mt-1 flex items-center gap-1 text-2xs text-ink-2">
                  <CornerDownRight className="size-3" /> Evidence: rows 1–2 of the result
                </p>
              </div>
            ) : null}
          </div>

          <ol className="grid min-w-0 content-start gap-2.5 border-t border-line pt-4 md:border-t-0 md:border-l md:pt-0 md:pl-5">
            {shownSteps.map((s) => (
              <li key={s.id} className="flex min-w-0 items-start gap-2">
                <span
                  className={`mt-0.5 grid size-4 shrink-0 place-items-center rounded-full ${s.status === "failed" ? "bg-amber-100 text-amber-ink" : "bg-forest-50 text-forest"}`}
                >
                  {s.status === "failed" ? (
                    <RotateCcw className="size-2.5" />
                  ) : (
                    <Check className="size-2.5" strokeWidth={3} />
                  )}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-xs font-medium text-ink">{s.label}</span>
                  <span className="block truncate text-2xs text-ink-2">{s.detail}</span>
                </span>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </div>
  );
}
