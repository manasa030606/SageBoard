// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ResultTable } from "@/types/domain";

import { ResultTableView } from "./result-table";

afterEach(cleanup);

const table: ResultTable = {
  columns: [
    { name: "category", label: "Category", format: "text" },
    { name: "revenue", label: "Revenue", format: "currency" },
    { name: "growth", label: "Growth", format: "percent" },
  ],
  rows: [
    { category: "Books", revenue: 1200, growth: 0.1 },
    { category: "Garden", revenue: 5000, growth: -0.05 },
    { category: "Toys", revenue: 300, growth: 0 },
  ],
  rowCount: 3,
  truncated: false,
};

const firstColumn = () =>
  screen
    .getAllByRole("row")
    .slice(1)
    .map((r) => within(r).getAllByRole("cell")[0]?.textContent);

describe("ResultTableView", () => {
  it("renders headers, rows and the row count", () => {
    render(<ResultTableView table={table} />);
    expect(screen.getByRole("button", { name: /Category/ })).toBeTruthy();
    expect(firstColumn()).toEqual(["Books", "Garden", "Toys"]);
    expect(screen.getByText("3 rows")).toBeTruthy();
  });

  it("says when the result was cut at the row limit and uses the singular for one row", () => {
    render(<ResultTableView table={{ ...table, rowCount: 5000, truncated: true }} />);
    expect(screen.getByText(/5,000 rows · truncated at the row limit/)).toBeTruthy();
    cleanup();
    render(<ResultTableView table={{ ...table, rows: table.rows.slice(0, 1), rowCount: 1 }} />);
    expect(screen.getByText("1 row")).toBeTruthy();
  });

  it("sorts descending, then ascending, then back to the original order", () => {
    render(<ResultTableView table={table} />);
    const header = screen.getByRole("button", { name: /Revenue/ });
    fireEvent.click(header);
    expect(firstColumn()).toEqual(["Garden", "Books", "Toys"]);
    expect(header.closest("th")?.getAttribute("aria-sort")).toBe("descending");
    fireEvent.click(header);
    expect(firstColumn()).toEqual(["Toys", "Books", "Garden"]);
    expect(header.closest("th")?.getAttribute("aria-sort")).toBe("ascending");
    fireEvent.click(header);
    expect(firstColumn()).toEqual(["Books", "Garden", "Toys"]);
  });

  it("keeps evidence highlighting on the same row after sorting", () => {
    const { container } = render(<ResultTableView table={table} highlightRows={[1]} />);
    fireEvent.click(screen.getByRole("button", { name: /Revenue/ }));
    const highlighted = container.querySelectorAll("[data-highlighted]");
    expect(highlighted).toHaveLength(1);
    expect(highlighted[0]?.textContent).toContain("Garden");
  });

  it("signs percent changes and shows a dash for missing values", () => {
    render(
      <ResultTableView
        table={{
          ...table,
          rows: [
            { category: "Books", revenue: 1, growth: 0.1 },
            { category: "Gap", growth: -0.05 } as never,
          ],
        }}
      />,
    );
    expect(screen.getByText(/^\+/)).toBeTruthy();
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("exports the table as a CSV file", () => {
    const click = vi.fn();
    const created: string[] = [];
    vi.stubGlobal("URL", {
      createObjectURL: (b: Blob) => (created.push(String(b.size)), "blob:x"),
      revokeObjectURL: vi.fn(),
    });
    const original = document.createElement.bind(document);
    vi.spyOn(document, "createElement").mockImplementation((tag: string) => {
      const el = original(tag);
      if (tag === "a") el.click = click;
      return el;
    });
    render(<ResultTableView table={table} fileName="revenue" />);
    fireEvent.click(screen.getByRole("button", { name: /Export CSV/ }));
    expect(click).toHaveBeenCalledOnce();
    expect(created).toHaveLength(1);
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });
});
