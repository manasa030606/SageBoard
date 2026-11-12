import type { Metadata } from "next";
import { Suspense } from "react";

import { Skeleton } from "@/components/ui/states";
import { AnalystWorkspace } from "@/features/analyst/analyst-workspace";
import { listConversations, listDatasets, listHistory, listScenarios, NOW } from "@/lib/data";

export const metadata: Metadata = { title: "Analyst" };

export default function AnalystPage() {
  const history = listHistory();
  const conversations = listConversations();
  const conversationScenario = Object.fromEntries(
    conversations.flatMap((c) => {
      const scenarioId = history.find((h) => h.id === c.runIds[0])?.scenarioId;
      return scenarioId ? [[c.id, scenarioId]] : [];
    }),
  );

  return (
    // useSearchParams (deep links) requires a Suspense boundary under Cache Components.
    <Suspense fallback={<WorkspaceFallback />}>
      <AnalystWorkspace
        datasets={listDatasets()}
        scenarios={listScenarios()}
        conversations={conversations}
        conversationScenario={conversationScenario}
        nowIso={NOW.toISOString()}
      />
    </Suspense>
  );
}

function WorkspaceFallback() {
  return (
    <div
      className="mx-auto grid max-w-[820px] gap-4 px-6 py-16"
      aria-busy="true"
      aria-label="Loading analyst"
    >
      <Skeleton className="h-3 w-32" />
      <Skeleton className="h-10 w-96 max-w-full" />
      <Skeleton className="h-4 w-full max-w-lg" />
    </div>
  );
}
