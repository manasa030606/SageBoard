import type { Metadata } from "next";

import { PageContainer } from "@/components/shell/app-shell";
import { HistoryScreen } from "@/features/history/history-screen";

export const metadata: Metadata = { title: "History" };

export default function HistoryPage() {
  return (
    <PageContainer wide>
      <HistoryScreen />
    </PageContainer>
  );
}
