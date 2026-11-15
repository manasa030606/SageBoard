"use client";

import { useState } from "react";

import { PageHeader } from "@/components/ui/layout";
import { Tabs } from "@/components/ui/tabs";

import { AnalysisHistory } from "./analysis-history";
import { QueryHistory } from "./query-history";

type View = "analyses" | "sql";

export function HistoryScreen() {
  const [view, setView] = useState<View>("analyses");
  return (
    <>
      <PageHeader
        eyebrow="History"
        title="Past analyses"
        description="Every question you’ve asked, with its plan, SQL, results and insights. Reopen one, keep going in its conversation, or turn it into a PDF report."
      />
      <Tabs
        className="mt-8"
        label="History views"
        value={view}
        onChange={setView}
        items={[
          { key: "analyses", label: "Analyses" },
          { key: "sql", label: "SQL log" },
        ]}
        renderPanel={(key) => (
          <div className="mt-6">
            {key === "analyses" ? <AnalysisHistory /> : <QueryHistory embedded />}
          </div>
        )}
      />
    </>
  );
}
