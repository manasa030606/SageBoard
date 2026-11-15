import { describe, expect, it } from "vitest";

import { escapeCsvCell } from "./csv";
import { tokenizeSql } from "./sql-highlight";

describe("tokenizeSql", () => {
  it("round-trips queries exactly, whitespace and comments included", () => {
    const queries = [
      "SELECT region, SUM(total) AS revenue\nFROM orders\nWHERE status <> 'cancelled'\nGROUP BY region\nORDER BY revenue DESC\nLIMIT 10",
      "SELECT 1 -- trailing comment",
      "  SELECT\t*  FROM   t ;  ",
    ];
    for (const sql of queries) {
      expect(
        tokenizeSql(sql)
          .map((t) => t.text)
          .join(""),
      ).toBe(sql);
    }
  });

  it("classifies keywords, functions, strings, numbers and comments", () => {
    const tokens = tokenizeSql(
      "SELECT SUM(x) FROM t WHERE s <> 'cancelled' LIMIT 10 -- note",
    ).filter((t) => t.type !== "space");
    const byText = Object.fromEntries(tokens.map((t) => [t.text, t.type]));
    expect(byText.SELECT).toBe("keyword");
    expect(byText.SUM).toBe("function");
    expect(byText["'cancelled'"]).toBe("string");
    expect(byText["10"]).toBe("number");
    expect(byText["-- note"]).toBe("comment");
    expect(byText.t).toBe("identifier");
  });

  it("does not treat a column named like a function as a function", () => {
    const tokens = tokenizeSql("SELECT count FROM t");
    expect(tokens.find((t) => t.text === "count")?.type).toBe("identifier");
  });
});

describe("escapeCsvCell", () => {
  it("neutralises spreadsheet formulas but keeps numbers", () => {
    expect(escapeCsvCell("=HYPERLINK(1)")).toBe("'=HYPERLINK(1)");
    expect(escapeCsvCell("@cmd")).toBe("'@cmd");
    expect(escapeCsvCell(-12.5)).toBe("-12.5");
    expect(escapeCsvCell('say "hi", ok')).toBe('"say ""hi"", ok"');
  });
});
