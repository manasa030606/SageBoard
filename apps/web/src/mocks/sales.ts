/*
 * DEMO DATA — Phase 2 only.
 *
 * Base series for the bundled "Retail demo" dataset. Generated once with a seeded
 * script (Nov 2024 – Oct 2026). Every figure shown in the UI (KPIs, regional
 * totals, sample-run tables and insight numbers) is DERIVED from these arrays in
 * src/lib/data/*, never typed by hand, so the numbers are always consistent.
 */

/** [month, revenue (USD), orders, active customers] */
export const MONTHLY_SERIES: ReadonlyArray<readonly [string, number, number, number]> = [
  ["2024-11", 671341, 4535, 3289],
  ["2024-12", 791892, 5385, 3954],
  ["2025-01", 458036, 3040, 2211],
  ["2025-02", 453126, 3031, 2177],
  ["2025-03", 528189, 3526, 2507],
  ["2025-04", 553363, 3731, 2752],
  ["2025-05", 608198, 3993, 2889],
  ["2025-06", 625674, 4050, 2878],
  ["2025-07", 599276, 3959, 2945],
  ["2025-08", 615811, 4059, 2891],
  ["2025-09", 653159, 4234, 3117],
  ["2025-10", 661336, 4367, 3215],
  ["2025-11", 772038, 4939, 3574],
  ["2025-12", 873751, 5691, 4091],
  ["2026-01", 539256, 3514, 2623],
  ["2026-02", 506879, 3239, 2378],
  ["2026-03", 600270, 3770, 2683],
  ["2026-04", 634280, 4087, 3032],
  ["2026-05", 671828, 4245, 3085],
  ["2026-06", 683898, 4360, 3214],
  ["2026-07", 663119, 4223, 3088],
  ["2026-08", 699057, 4452, 3281],
  ["2026-09", 732470, 4619, 3419],
  ["2026-10", 748662, 4723, 3360],
];

/** Distinct customers who ordered in each 12-month window (from the customers table). */
export const UNIQUE_CUSTOMERS = { last12: 18642, previous12: 16905 } as const;

/**
 * Regional weights for Q2 and Q3 2026. Absolute regional revenue is computed by
 * splitting each quarter's monthly total by these weights.
 */
export const REGION_WEIGHTS: ReadonlyArray<{ region: string; q2: number; q3: number }> = [
  { region: "Northeast", q2: 472340, q3: 486982 },
  { region: "Southeast", q2: 383828, q3: 429120 },
  { region: "Midwest", q2: 344486, q3: 336218 },
  { region: "Southwest", q2: 278898, q3: 302326 },
  { region: "West", q2: 363156, q3: 382041 },
  { region: "Pacific Northwest", q2: 161699, q3: 183851 },
];

/** Top products: share of year-to-date (Jan–Oct 2026) revenue, list price and growth vs same period 2025. */
export const PRODUCT_MIX: ReadonlyArray<{
  sku: string;
  name: string;
  category: string;
  share: number;
  price: number;
  growth: number;
}> = [
  {
    sku: "HM-1042",
    name: "Linen Duvet Set",
    category: "Home",
    share: 0.0472,
    price: 189,
    growth: 0.214,
  },
  {
    sku: "KT-2210",
    name: "Cast Iron Dutch Oven",
    category: "Kitchen",
    share: 0.0418,
    price: 129,
    growth: 0.087,
  },
  {
    sku: "OD-3307",
    name: "Trail Daypack 28L",
    category: "Outdoor",
    share: 0.0361,
    price: 98,
    growth: 0.312,
  },
  {
    sku: "HM-1188",
    name: "Wool Throw Blanket",
    category: "Home",
    share: 0.0329,
    price: 84,
    growth: 0.046,
  },
  {
    sku: "EL-4415",
    name: "Wireless Speaker Mini",
    category: "Electronics",
    share: 0.0301,
    price: 79,
    growth: -0.058,
  },
  {
    sku: "KT-2291",
    name: "Pour-Over Coffee Kit",
    category: "Kitchen",
    share: 0.0284,
    price: 56,
    growth: 0.163,
  },
  {
    sku: "AP-5120",
    name: "Merino Crew Sweater",
    category: "Apparel",
    share: 0.0262,
    price: 112,
    growth: 0.071,
  },
  {
    sku: "OD-3354",
    name: "Insulated Bottle 750ml",
    category: "Outdoor",
    share: 0.0247,
    price: 34,
    growth: 0.129,
  },
  {
    sku: "HM-1203",
    name: "Stoneware Dinner Set",
    category: "Home",
    share: 0.0233,
    price: 142,
    growth: -0.021,
  },
  {
    sku: "EL-4472",
    name: "Smart Desk Lamp",
    category: "Electronics",
    share: 0.0219,
    price: 68,
    growth: 0.054,
  },
];

/** Customer segments over the last 12 months: share of orders and of revenue. */
export const SEGMENT_MIX: ReadonlyArray<{
  segment: string;
  orderShare: number;
  revenueShare: number;
}> = [
  { segment: "Consumer", orderShare: 0.71, revenueShare: 0.58 },
  { segment: "Small business", orderShare: 0.23, revenueShare: 0.29 },
  { segment: "Enterprise", orderShare: 0.06, revenueShare: 0.13 },
];

/** The demo's "today": data is complete through October 2026. */
export const DEMO_NOW = new Date("2026-11-12T14:30:00Z");
