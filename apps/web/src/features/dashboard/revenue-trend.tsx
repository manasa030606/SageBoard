"use client";

import { useState } from "react";

import { LineChartView } from "@/components/charts/charts";
import { ResultTableView } from "@/components/data/result-table";
import { Segmented } from "@/components/ui/tabs";
import type { DashboardSummary } from "@/types/domain";

export function RevenueTrend({ data }: { data: DashboardSummary["revenueTrend"] }) {
  const [view, setView] = useState<"chart" | "table">("chart");
  const rows = data.map((d) => ({ ...d }));
  return (
    <section aria-labelledby="trend-heading" className="flex h-full min-w-0 flex-col">
      <div className="mb-3 flex items-end justify-between gap-4">
        <div>
          <h2 id="trend-heading" className="text-[15px] font-semibold text-ink">
            Revenue trend
          </h2>
          <p className="mt-0.5 text-[13px] text-ink-2">
            Monthly revenue vs the same month a year earlier
          </p>
        </div>
        <Segmented
          label="Revenue trend view"
          value={view}
          onChange={setView}
          options={[
            { key: "chart", label: "Chart" },
            { key: "table", label: "Table" },
          ]}
        />
      </div>
      <div className="flex-1 rounded-md border border-line bg-paper px-3 pt-5 pb-3">
        {view === "chart" ? (
          <LineChartView
            data={rows}
            x="month"
            ariaLabel="Monthly revenue, last 12 months versus prior year"
            valueFormat="currency"
            height={340}
            series={[
              { key: "previous", label: "Previous year", muted: true, color: "var(--color-ink-3)" },
              { key: "current", label: "Last 12 months", color: "var(--color-series-1)" },
            ]}
          />
        ) : (
          <ResultTableView
            fileName="revenue-trend"
            maxHeight={300}
            table={{
              columns: [
                { name: "month", label: "Month", format: "month" },
                { name: "current", label: "Revenue", format: "currency" },
                { name: "previous", label: "Prior year", format: "currency" },
              ],
              rows,
              rowCount: rows.length,
              truncated: false,
            }}
          />
        )}
      </div>
    </section>
  );
}
