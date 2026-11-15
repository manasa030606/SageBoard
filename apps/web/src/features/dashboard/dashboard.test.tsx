// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { datasets, history, reports } from "@/lib/api/endpoints";

import { Dashboard } from "./dashboard";

vi.mock("@/lib/api/endpoints", () => ({
  datasets: { list: vi.fn() },
  history: { sessions: vi.fn() },
  reports: { list: vi.fn() },
}));

const emptyPage = { items: [], next_cursor: null };

afterEach(cleanup);

beforeEach(() => {
  vi.mocked(datasets.list).mockResolvedValue([]);
  vi.mocked(history.sessions).mockResolvedValue(emptyPage);
  vi.mocked(reports.list).mockResolvedValue(emptyPage);
});

describe("Dashboard", () => {
  it("shows an empty state in every section for a new account", async () => {
    render(<Dashboard />);
    expect(await screen.findByText("No datasets yet")).toBeTruthy();
    expect(await screen.findByText("No analyses yet")).toBeTruthy();
    expect(await screen.findByText("No reports yet")).toBeTruthy();
  });

  it("lists real datasets and reports returned by the API", async () => {
    vi.mocked(datasets.list).mockResolvedValue([
      {
        id: "d1",
        name: "Sales 2026",
        description: null,
        source_type: "upload_csv",
        file_name: "sales.csv",
        status: "ready",
        status_reason: null,
        version: 1,
        total_rows: 1200,
        size_bytes: 1000,
        table_count: 1,
        created_at: "2026-11-01T00:00:00Z",
        updated_at: "2026-11-01T00:00:00Z",
      },
    ]);
    vi.mocked(reports.list).mockResolvedValue({
      items: [
        {
          id: "r1",
          title: "Revenue by region",
          analysis_session_id: null,
          dataset_id: "d1",
          created_at: "2026-11-02T00:00:00Z",
          updated_at: "2026-11-02T00:00:00Z",
        },
      ],
      next_cursor: null,
    });
    render(<Dashboard />);
    expect(await screen.findByText("Sales 2026")).toBeTruthy();
    expect(screen.getByText(/1 table · 1,200 rows/)).toBeTruthy();
    expect(await screen.findByText("Revenue by region")).toBeTruthy();
  });

  it("shows an error with a retry button when a section fails to load", async () => {
    vi.mocked(history.sessions).mockRejectedValue(new Error("boom"));
    render(<Dashboard />);
    expect(await screen.findByText("Couldn’t load this section")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
  });
});
