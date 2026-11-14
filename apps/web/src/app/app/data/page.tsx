import type { Metadata } from "next";

import { PageContainer } from "@/components/shell/app-shell";
import { DataSources } from "@/features/data/data-sources";

export const metadata: Metadata = { title: "Data sources" };

export default function DataPage() {
  return (
    <PageContainer wide>
      <DataSources />
    </PageContainer>
  );
}
