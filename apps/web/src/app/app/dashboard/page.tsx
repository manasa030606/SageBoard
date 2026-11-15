import type { Metadata } from "next";

import { PageContainer } from "@/components/shell/app-shell";
import { Dashboard } from "@/features/dashboard/dashboard";

export const metadata: Metadata = { title: "Dashboard" };

export default function DashboardPage() {
  return (
    <PageContainer>
      <Dashboard />
    </PageContainer>
  );
}
