import type { Metadata } from "next";
import { Suspense } from "react";

import { LiveAnalystWorkspace } from "@/features/analyst/live/workspace";

export const metadata: Metadata = { title: "Analyst" };

export default function AnalystPage() {
  // useSearchParams (the ?conversation= deep link from History) needs a Suspense boundary.
  return (
    <Suspense fallback={null}>
      <LiveAnalystWorkspace />
    </Suspense>
  );
}
