import type { Metadata } from "next";

import { PageContainer } from "@/components/shell/app-shell";
import { QueryHistory } from "@/features/history/query-history";

export const metadata: Metadata = { title: "Query history" };

export default function HistoryPage() {
  return (
    <PageContainer wide>
      <QueryHistory />
    </PageContainer>
  );
}
