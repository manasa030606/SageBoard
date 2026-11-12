/* DEMO DATA — Phase 2 only. Replaced by GET /api/v1/datasets in a later phase. */
import type { ColumnType, Dataset, DatasetColumn, SemanticRole } from "@/types/domain";

function col(
  name: string,
  type: ColumnType,
  opts: {
    role?: SemanticRole;
    description?: string;
    distinct: number;
    nullPct?: number;
    min?: string;
    max?: string;
    top?: [string, number][];
    sensitive?: boolean;
    display?: string;
  },
): DatasetColumn {
  return {
    name,
    displayName: opts.display ?? name.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase()),
    type,
    semanticRole: opts.role ?? null,
    description: opts.description ?? null,
    isSensitive: opts.sensitive ?? false,
    profile: {
      nullPct: opts.nullPct ?? 0,
      distinctCount: opts.distinct,
      min: opts.min ?? null,
      max: opts.max ?? null,
      topValues: (opts.top ?? []).map(([value, count]) => ({ value, count })),
    },
  };
}

const retailDemo: Dataset = {
  id: "ds_retail_demo",
  name: "Retail demo",
  description:
    "Two years of orders for a home & lifestyle retailer across six US regions. Bundled sample dataset.",
  sourceType: "sample",
  fileName: null,
  status: "ready",
  statusReason: null,
  totalRows: 213_318,
  sizeBytes: 38_400_000,
  version: 3,
  createdAt: "2026-09-02T09:12:00Z",
  updatedAt: "2026-11-01T06:00:00Z",
  tables: [
    {
      name: "orders",
      displayName: "Orders",
      description: "One row per customer order.",
      rowCount: 101_232,
      columns: [
        col("order_id", "bigint", {
          role: "identifier",
          distinct: 101_232,
          min: "100001",
          max: "201232",
        }),
        col("customer_id", "bigint", { role: "identifier", distinct: 24_118 }),
        col("order_date", "date", {
          role: "time",
          distinct: 730,
          min: "2024-11-01",
          max: "2026-10-31",
        }),
        col("status", "text", {
          role: "dimension",
          description: "Cancelled orders are excluded from revenue.",
          distinct: 4,
          top: [
            ["delivered", 93_874],
            ["shipped", 3_412],
            ["cancelled", 2_906],
            ["returned", 1_040],
          ],
        }),
        col("channel", "text", {
          role: "dimension",
          distinct: 3,
          top: [
            ["web", 61_903],
            ["store", 27_115],
            ["marketplace", 12_214],
          ],
        }),
        col("region_id", "integer", { role: "identifier", distinct: 6 }),
      ],
    },
    {
      name: "order_items",
      displayName: "Order items",
      description: "Line items. Revenue = quantity × unit_price × (1 − discount).",
      rowCount: 84_406,
      columns: [
        col("order_id", "bigint", { role: "identifier", distinct: 101_232 }),
        col("product_id", "integer", { role: "identifier", distinct: 148 }),
        col("quantity", "integer", { role: "measure", distinct: 12, min: "1", max: "24" }),
        col("unit_price", "numeric", {
          role: "currency",
          distinct: 312,
          min: "6.00",
          max: "489.00",
        }),
        col("discount", "numeric", {
          role: "measure",
          distinct: 9,
          min: "0.00",
          max: "0.40",
          nullPct: 0,
        }),
      ],
    },
    {
      name: "products",
      displayName: "Products",
      description: "Product catalogue.",
      rowCount: 148,
      columns: [
        col("product_id", "integer", { role: "identifier", distinct: 148 }),
        col("sku", "text", { role: "identifier", distinct: 148 }),
        col("name", "text", { role: "dimension", distinct: 148 }),
        col("category", "text", {
          role: "dimension",
          distinct: 5,
          top: [
            ["Home", 41],
            ["Kitchen", 36],
            ["Outdoor", 28],
            ["Apparel", 24],
            ["Electronics", 19],
          ],
        }),
        col("list_price", "numeric", {
          role: "currency",
          distinct: 121,
          min: "6.00",
          max: "489.00",
        }),
      ],
    },
    {
      name: "customers",
      displayName: "Customers",
      description: "Customer accounts.",
      rowCount: 27_526,
      columns: [
        col("customer_id", "bigint", { role: "identifier", distinct: 27_526 }),
        col("email", "text", {
          distinct: 27_526,
          sensitive: true,
          description: "Never sent to the model.",
        }),
        col("segment", "text", {
          role: "dimension",
          distinct: 3,
          top: [
            ["Consumer", 21_204],
            ["Small business", 5_301],
            ["Enterprise", 1_021],
          ],
        }),
        col("region_id", "integer", { role: "identifier", distinct: 6 }),
        col("signup_date", "date", {
          role: "time",
          distinct: 1_644,
          min: "2019-03-04",
          max: "2026-10-30",
        }),
      ],
    },
    {
      name: "regions",
      displayName: "Regions",
      description: null,
      rowCount: 6,
      columns: [
        col("region_id", "integer", { role: "identifier", distinct: 6 }),
        col("name", "text", { role: "dimension", distinct: 6 }),
      ],
    },
  ],
};

const marketingSpend: Dataset = {
  id: "ds_marketing_2026",
  name: "Marketing spend 2026",
  description: "Weekly paid-media spend and attributed sessions by channel.",
  sourceType: "upload_csv",
  fileName: "marketing_spend_2026.csv",
  status: "ready",
  statusReason: null,
  totalRows: 1_872,
  sizeBytes: 214_000,
  version: 1,
  createdAt: "2026-11-04T11:41:00Z",
  updatedAt: "2026-11-04T11:42:00Z",
  tables: [
    {
      name: "marketing_spend_2026",
      displayName: "Marketing spend 2026",
      description: null,
      rowCount: 1_872,
      columns: [
        col("week_start", "date", {
          role: "time",
          distinct: 44,
          min: "2026-01-05",
          max: "2026-11-02",
        }),
        col("channel", "text", {
          role: "dimension",
          distinct: 6,
          top: [
            ["Search", 312],
            ["Social", 312],
            ["Display", 312],
          ],
        }),
        col("spend_usd", "numeric", {
          role: "currency",
          distinct: 1_760,
          min: "120.00",
          max: "48210.00",
        }),
        col("sessions", "integer", {
          role: "measure",
          distinct: 1_701,
          nullPct: 0.012,
          min: "210",
          max: "91833",
        }),
      ],
    },
  ],
};

const supportTickets: Dataset = {
  id: "ds_support_tickets",
  name: "Support tickets",
  description: "Helpdesk export, Q3 2026.",
  sourceType: "upload_csv",
  fileName: "support_tickets_q3.csv",
  status: "loading",
  statusReason: "Loading rows and computing column profiles…",
  totalRows: 0,
  sizeBytes: 6_900_000,
  version: 1,
  createdAt: "2026-11-12T14:21:00Z",
  updatedAt: "2026-11-12T14:21:00Z",
  tables: [],
};

const inventory: Dataset = {
  id: "ds_inventory",
  name: "Inventory snapshot",
  description: "Warehouse stock levels.",
  sourceType: "upload_xlsx",
  fileName: "inventory_snapshot.xlsx",
  status: "failed",
  statusReason:
    'Column "qty_on_hand" was set to integer, but 214 rows contain text such as "N/A". Change the type to text or clean those rows and upload again.',
  totalRows: 0,
  sizeBytes: 1_300_000,
  version: 1,
  createdAt: "2026-11-10T08:03:00Z",
  updatedAt: "2026-11-10T08:04:00Z",
  tables: [],
};

export const DATASETS: readonly Dataset[] = [retailDemo, marketingSpend, supportTickets, inventory];
