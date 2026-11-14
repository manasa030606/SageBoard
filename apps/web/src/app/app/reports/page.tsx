import type { Metadata } from "next";

import { PageContainer } from "@/components/shell/app-shell";
import { ReportsList } from "@/features/reports/reports-list";

export const metadata: Metadata = { title: "Reports" };

export default function ReportsPage() {
  return (
    <PageContainer>
      <ReportsList />
    </PageContainer>
  );
}
