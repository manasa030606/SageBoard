import type { Metadata } from "next";

import { PageContainer } from "@/components/shell/app-shell";
import { QueryHistory } from "@/features/history/query-history";
import { listDatasets, listHistory, NOW } from "@/lib/data";

export const metadata: Metadata = { title: "Query history" };

export default function HistoryPage() {
  return (
    <PageContainer wide>
      <QueryHistory entries={listHistory()} datasets={listDatasets()} nowIso={NOW.toISOString()} />
    </PageContainer>
  );
}
