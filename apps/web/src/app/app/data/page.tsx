import type { Metadata } from "next";

import { PageContainer } from "@/components/shell/app-shell";
import { DataSources } from "@/features/data/data-sources";
import { listDatasets, NOW } from "@/lib/data";

export const metadata: Metadata = { title: "Data sources" };

export default function DataPage() {
  return (
    <PageContainer wide>
      <DataSources datasets={listDatasets()} nowIso={NOW.toISOString()} />
    </PageContainer>
  );
}
