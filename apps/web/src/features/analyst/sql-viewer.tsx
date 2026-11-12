"use client";

import { Check, Copy } from "lucide-react";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/cn";
import { tokenizeSql, type SqlTokenType } from "@/lib/sql-highlight";
import type { SqlAttempt } from "@/types/domain";

const TOKEN_CLASS: Record<SqlTokenType, string> = {
  keyword: "text-forest font-medium",
  function: "text-navy-600",
  string: "text-amber-ink",
  number: "text-amber-ink",
  comment: "text-ink-3 italic",
  operator: "text-ink-3",
  identifier: "text-ink",
  space: "",
};

export function SqlCode({ sql }: { sql: string }) {
  const tokens = useMemo(() => tokenizeSql(sql), [sql]);
  const lines = sql.split("\n").length;
  return (
    <div className="flex overflow-x-auto bg-warm/50 font-mono text-[12.5px] leading-[1.7]">
      <div
        aria-hidden
        className="shrink-0 border-r border-line py-3 pr-3 pl-4 text-right text-ink-3 tabular select-none"
      >
        {Array.from({ length: lines }, (_, i) => (
          <div key={i}>{i + 1}</div>
        ))}
      </div>
      <pre className="min-w-0 flex-1 py-3 pr-4 pl-4">
        <code>
          {tokens.map((t, i) => (
            <span key={i} className={TOKEN_CLASS[t.type]}>
              {t.text}
            </span>
          ))}
        </code>
      </pre>
    </div>
  );
}

const STATUS_BADGE: Record<
  SqlAttempt["status"],
  { tone: "positive" | "warning" | "critical"; label: string }
> = {
  accepted: { tone: "positive", label: "Accepted · executed" },
  rejected: { tone: "warning", label: "Rejected by validator" },
  failed: { tone: "critical", label: "Database error" },
};

export function SqlViewer({ attempts }: { attempts: SqlAttempt[] }) {
  const [selected, setSelected] = useState(attempts.length - 1);
  const [copied, setCopied] = useState(false);
  const attempt = attempts[selected];
  if (!attempt) return null;
  const badge = STATUS_BADGE[attempt.status];

  async function copy() {
    if (!attempt) return;
    try {
      await navigator.clipboard.writeText(attempt.sql);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-2.5">
        <div className="flex items-center gap-2">
          {attempts.length > 1 ? (
            <div role="group" aria-label="Query attempts" className="flex gap-1">
              {attempts.map((a, i) => (
                <button
                  key={a.attempt}
                  type="button"
                  onClick={() => setSelected(i)}
                  aria-pressed={i === selected}
                  className={cn(
                    "h-7 rounded-xs px-2 text-xs font-medium transition-colors",
                    i === selected
                      ? "bg-navy text-warm"
                      : "text-ink-2 hover:bg-warm-200 hover:text-ink",
                  )}
                >
                  Attempt {a.attempt}
                </button>
              ))}
            </div>
          ) : (
            <span className="text-xs font-medium text-ink-2">Attempt 1</span>
          )}
          <Badge tone={badge.tone} dot>
            {badge.label}
          </Badge>
        </div>
        <div className="flex items-center gap-3 text-xs text-ink-2">
          {attempt.rowCount !== null ? (
            <span className="tabular">
              {attempt.rowCount} rows{attempt.execMs !== null ? ` · ${attempt.execMs} ms` : ""}
            </span>
          ) : null}
          <button
            type="button"
            onClick={copy}
            className="inline-flex h-7 items-center gap-1.5 rounded-xs px-2 font-medium text-ink-2 hover:bg-warm-200 hover:text-ink"
          >
            {copied ? (
              <Check className="size-3.5 text-forest" aria-hidden />
            ) : (
              <Copy className="size-3.5" aria-hidden />
            )}
            {copied ? "Copied" : "Copy SQL"}
          </button>
        </div>
      </div>
      {attempt.violations.length > 0 ? (
        <ul
          className={cn(
            "border-b px-4 py-2.5 text-[12.5px]",
            attempt.status === "failed"
              ? "border-rust/20 bg-rust-50"
              : "border-amber/30 bg-amber-100/60",
          )}
        >
          {attempt.violations.map((v) => (
            <li key={v.code} className="flex gap-2">
              <code
                className={cn(
                  "shrink-0 font-medium",
                  attempt.status === "failed" ? "text-rust" : "text-amber-ink",
                )}
              >
                {v.code}
              </code>
              <span className="text-ink">{v.message}</span>
            </li>
          ))}
        </ul>
      ) : null}
      <SqlCode sql={attempt.sql} />
    </div>
  );
}
