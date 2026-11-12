/*
 * Pure derivations over the demo sales series. Everything here is deterministic
 * and unit-tested (analytics.test.ts) so dashboard figures, sample-run tables and
 * insight sentences always agree with each other.
 */
import {
  DEMO_NOW,
  MONTHLY_SERIES,
  PRODUCT_MIX,
  REGION_WEIGHTS,
  SEGMENT_MIX,
  UNIQUE_CUSTOMERS,
} from "@/mocks/sales";
import type {
  DashboardSummary,
  Kpi,
  MonthlyMetric,
  ProductPerformance,
  RegionPerformance,
} from "@/types/domain";

export function monthlyMetrics(): MonthlyMetric[] {
  return MONTHLY_SERIES.map(([month, revenue, orders, activeCustomers]) => ({
    month,
    revenue,
    orders,
    activeCustomers,
  }));
}

export const sum = (values: readonly number[]): number => values.reduce((acc, v) => acc + v, 0);

/** Split an integer total by weights so the parts add up to the total exactly. */
export function splitByWeights(total: number, weights: readonly number[]): number[] {
  const weightSum = sum(weights);
  const parts = weights.map((w) => Math.round((total * w) / weightSum));
  const drift = total - sum(parts);
  if (parts.length > 0) parts[parts.length - 1] = (parts[parts.length - 1] ?? 0) + drift;
  return parts;
}

export function growth(current: number, previous: number): number | null {
  return previous === 0 ? null : (current - previous) / previous;
}

function window(months: MonthlyMetric[], from: string, to: string): MonthlyMetric[] {
  return months.filter((m) => m.month >= from && m.month <= to);
}

export const PERIODS = {
  last12: { from: "2025-11", to: "2026-10", label: "Nov 2025 – Oct 2026" },
  previous12: { from: "2024-11", to: "2025-10", label: "Nov 2024 – Oct 2025" },
  q2: { from: "2026-04", to: "2026-06", label: "Q2 2026" },
  q3: { from: "2026-07", to: "2026-09", label: "Q3 2026" },
  ytd: { from: "2026-01", to: "2026-10", label: "Jan – Oct 2026" },
} as const;

export function periodTotals(key: keyof typeof PERIODS) {
  const p = PERIODS[key];
  const rows = window(monthlyMetrics(), p.from, p.to);
  return {
    months: rows,
    revenue: sum(rows.map((r) => r.revenue)),
    orders: sum(rows.map((r) => r.orders)),
  };
}

export function regionPerformance(): RegionPerformance[] {
  const q2 = periodTotals("q2");
  const q3 = periodTotals("q3");
  const q2Parts = splitByWeights(
    q2.revenue,
    REGION_WEIGHTS.map((r) => r.q2),
  );
  const q3Parts = splitByWeights(
    q3.revenue,
    REGION_WEIGHTS.map((r) => r.q3),
  );
  const aov = q3.revenue / q3.orders;
  return REGION_WEIGHTS.map((r, i) => {
    const revenue = q3Parts[i] ?? 0;
    const previous = q2Parts[i] ?? 0;
    return {
      region: r.region,
      revenue,
      orders: Math.round(revenue / aov),
      growth: growth(revenue, previous) ?? 0,
    };
  }).sort((a, b) => b.revenue - a.revenue);
}

/** Q2 vs Q3 revenue per region (for the region-growth sample run). */
export function regionQuarterComparison() {
  const q2Parts = splitByWeights(
    periodTotals("q2").revenue,
    REGION_WEIGHTS.map((r) => r.q2),
  );
  const q3Parts = splitByWeights(
    periodTotals("q3").revenue,
    REGION_WEIGHTS.map((r) => r.q3),
  );
  return REGION_WEIGHTS.map((r, i) => {
    const q2 = q2Parts[i] ?? 0;
    const q3 = q3Parts[i] ?? 0;
    return { region: r.region, q2, q3, growth: growth(q3, q2) ?? 0 };
  }).sort((a, b) => b.growth - a.growth);
}

export function topProducts(): ProductPerformance[] {
  const ytd = periodTotals("ytd").revenue;
  const revenues = PRODUCT_MIX.map((p) => Math.round(ytd * p.share));
  return PRODUCT_MIX.map((p, i) => {
    const revenue = revenues[i] ?? 0;
    return {
      sku: p.sku,
      name: p.name,
      category: p.category,
      revenue,
      unitsSold: Math.round(revenue / p.price),
      growth: p.growth,
    };
  }).sort((a, b) => b.revenue - a.revenue);
}

export function segmentPerformance() {
  const { revenue, orders } = periodTotals("last12");
  const orderParts = splitByWeights(
    orders,
    SEGMENT_MIX.map((s) => s.orderShare),
  );
  const revenueParts = splitByWeights(
    revenue,
    SEGMENT_MIX.map((s) => s.revenueShare),
  );
  return SEGMENT_MIX.map((s, i) => {
    const segOrders = orderParts[i] ?? 0;
    const segRevenue = revenueParts[i] ?? 0;
    return {
      segment: s.segment,
      orders: segOrders,
      revenue: segRevenue,
      aov: Math.round((segRevenue / segOrders) * 100) / 100,
    };
  }).sort((a, b) => b.aov - a.aov);
}

export function getDashboardSummary(): DashboardSummary {
  const current = periodTotals("last12");
  const previous = periodTotals("previous12");
  const revenueGrowth = growth(current.revenue, previous.revenue) ?? 0;

  const kpis: Kpi[] = [
    {
      key: "revenue",
      label: "Total revenue",
      value: current.revenue,
      format: "currency",
      delta: growth(current.revenue, previous.revenue),
      comparisonLabel: "vs previous 12 months",
      sparkline: current.months.map((m) => m.revenue),
    },
    {
      key: "orders",
      label: "Total orders",
      value: current.orders,
      format: "integer",
      delta: growth(current.orders, previous.orders),
      comparisonLabel: "vs previous 12 months",
      sparkline: current.months.map((m) => m.orders),
    },
    {
      key: "customers",
      label: "Active customers",
      value: UNIQUE_CUSTOMERS.last12,
      format: "integer",
      delta: growth(UNIQUE_CUSTOMERS.last12, UNIQUE_CUSTOMERS.previous12),
      comparisonLabel: "distinct buyers, vs prior year",
      sparkline: current.months.map((m) => m.activeCustomers),
    },
    {
      key: "growth",
      label: "Revenue growth",
      value: revenueGrowth,
      format: "percent",
      delta: null,
      comparisonLabel: "year over year",
      sparkline: current.months.map((m, i) => {
        const prior = previous.months[i]?.revenue ?? m.revenue;
        return (m.revenue - prior) / prior;
      }),
    },
  ];

  return {
    periodLabel: PERIODS.last12.label,
    datasetName: "Retail demo",
    asOf: DEMO_NOW.toISOString(),
    kpis,
    revenueTrend: current.months.map((m, i) => ({
      month: m.month,
      current: m.revenue,
      previous: previous.months[i]?.revenue ?? 0,
    })),
    regions: regionPerformance(),
    topProducts: topProducts().slice(0, 6),
  };
}
