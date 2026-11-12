import { ArrowRight, MessageSquareText } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { PageContainer } from "@/components/shell/app-shell";
import { ButtonLink } from "@/components/ui/button";
import { PageHeader, Section } from "@/components/ui/layout";
import { KpiStrip } from "@/features/dashboard/kpi-strip";
import {
  RecentAnalyses,
  RegionList,
  TopProductsTable,
} from "@/features/dashboard/dashboard-tables";
import { RevenueTrend } from "@/features/dashboard/revenue-trend";
import { getDashboard, listHistory, NOW } from "@/lib/data";
import { formatDateTime } from "@/lib/format";

export const metadata: Metadata = { title: "Dashboard" };

export default function DashboardPage() {
  const summary = getDashboard();
  const recent = listHistory().slice(0, 5);

  return (
    <PageContainer wide>
      <PageHeader
        eyebrow={`${summary.datasetName} · ${summary.periodLabel}`}
        title="Overview"
        description="How the business performed over the last twelve complete months."
        actions={
          <>
            <span className="hidden text-xs text-ink-2 md:inline">
              Data refreshed {formatDateTime(summary.asOf)}
            </span>
            <ButtonLink
              href="/app/analyst"
              variant="primary"
              leadingIcon={<MessageSquareText className="size-4" aria-hidden />}
            >
              Ask a question
            </ButtonLink>
          </>
        }
      />

      <div className="mt-8 grid gap-8">
        <KpiStrip kpis={summary.kpis} />

        <div className="grid gap-8 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
          <RevenueTrend data={summary.revenueTrend} />
          <Section
            surface
            id="regions"
            title="Sales by region"
            description="Q3 2026 revenue · share · change vs Q2"
            bodyClassName="py-1"
          >
            <RegionList regions={summary.regions} />
          </Section>
        </div>

        <div className="grid gap-8 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
          <Section
            surface
            id="products"
            title="Top products"
            description="By revenue, January – October 2026"
            actions={
              <Link
                href="/app/analyst?sample=sc_products"
                className="inline-flex items-center gap-1 text-[13px] text-forest hover:underline"
              >
                Analyse <ArrowRight className="size-3.5" aria-hidden />
              </Link>
            }
          >
            <TopProductsTable products={summary.topProducts} />
          </Section>
          <Section
            surface
            id="recent"
            title="Recent analyses"
            description="Questions asked by your team"
            actions={
              <Link
                href="/app/history"
                className="inline-flex items-center gap-1 text-[13px] text-forest hover:underline"
              >
                View all <ArrowRight className="size-3.5" aria-hidden />
              </Link>
            }
            bodyClassName="py-1"
          >
            <RecentAnalyses entries={recent} now={NOW} />
          </Section>
        </div>
      </div>
    </PageContainer>
  );
}
