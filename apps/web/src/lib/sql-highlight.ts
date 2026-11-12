/*
 * Minimal SQL tokenizer for display-only syntax highlighting. It never changes the
 * text: concatenating every token's `text` returns the input exactly (tested).
 */
export type SqlTokenType =
  "keyword" | "function" | "string" | "number" | "comment" | "operator" | "identifier" | "space";

export interface SqlToken {
  type: SqlTokenType;
  text: string;
}

const KEYWORDS = new Set(
  `select from where and or not as on join left right inner outer full cross group by order having limit offset
   with case when then else end distinct union all intersect except asc desc nulls first last is null in between
   like ilike interval date filter over partition rows range true false exists`
    .split(/\s+/)
    .filter(Boolean),
);

const FUNCTIONS = new Set(
  `sum count avg min max round date_trunc extract coalesce nullif rank dense_rank row_number lag lead
   cast to_char greatest least abs percentile_cont stddev`
    .split(/\s+/)
    .filter(Boolean),
);

const PATTERNS: Array<[SqlTokenType, RegExp]> = [
  ["space", /^\s+/],
  ["comment", /^--[^\n]*/],
  ["string", /^'(?:[^']|'')*'?/],
  ["number", /^\d+(?:\.\d+)?\b/],
  ["operator", /^(?:::|<>|<=|>=|!=|\|\||[=<>+\-*/%(),.;])/],
  ["identifier", /^"(?:[^"]|"")*"?|^[A-Za-z_][A-Za-z0-9_]*/],
];

export function tokenizeSql(sql: string): SqlToken[] {
  const tokens: SqlToken[] = [];
  let rest = sql;
  while (rest.length > 0) {
    let matched = false;
    for (const [type, pattern] of PATTERNS) {
      const m = pattern.exec(rest);
      if (!m || m[0].length === 0) continue;
      const text = m[0];
      let finalType = type;
      if (type === "identifier" && !text.startsWith('"')) {
        const lower = text.toLowerCase();
        const nextChar = rest.slice(text.length).trimStart()[0];
        if (KEYWORDS.has(lower)) finalType = "keyword";
        else if (FUNCTIONS.has(lower) && nextChar === "(") finalType = "function";
      }
      tokens.push({ type: finalType, text });
      rest = rest.slice(text.length);
      matched = true;
      break;
    }
    if (!matched) {
      tokens.push({ type: "operator", text: rest[0] ?? "" });
      rest = rest.slice(1);
    }
  }
  return tokens;
}
