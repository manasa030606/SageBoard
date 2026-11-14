import type { Metadata } from "next";
import { Suspense } from "react";

import { PageContainer } from "@/components/shell/app-shell";
import { Skeleton } from "@/components/ui/states";
import { ReportView } from "@/features/reports/report-view";

export const metadata: Metadata = { title: "Report" };

export default function ReportPage() {
  return (
    <PageContainer className="max-w-[880px]">
      {/* The report id comes from the URL: only this part waits for it. */}
      <Suspense
        fallback={
          <div className="mt-10 grid gap-4" aria-busy="true">
            <Skeleton className="h-10 w-3/4" />
            <Skeleton className="h-24 w-full" />
          </div>
        }
      >
        <ReportView />
      </Suspense>
    </PageContainer>
  );
}
