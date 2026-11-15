import type { Metadata } from "next";

import { LiveAnalystWorkspace } from "@/features/analyst/live/workspace";

export const metadata: Metadata = { title: "Analyst" };

export default function AnalystPage() {
  return <LiveAnalystWorkspace />;
}
