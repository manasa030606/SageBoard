import type { Metadata } from "next";

import { PageContainer } from "@/components/shell/app-shell";
import { SettingsView } from "@/features/settings/settings-view";
import { getUsage, getUserSettings } from "@/lib/data";

export const metadata: Metadata = { title: "Settings" };

export default function SettingsPage() {
  return (
    <PageContainer>
      <SettingsView initial={getUserSettings()} usage={getUsage()} />
    </PageContainer>
  );
}
