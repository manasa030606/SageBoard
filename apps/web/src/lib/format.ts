import type { ValueFormat } from "@/types/domain";

/*
 * All number/date formatting goes through these helpers so the whole UI stays
 * consistent (and switching currency or locale is a one-line change).
 */
const LOCALE = "en-US";
const CURRENCY = "USD";
/** Fixed display timezone so server and browser render identical text (user setting later). */
const TIME_ZONE = "Asia/Kolkata";

const currencyFull = new Intl.NumberFormat(LOCALE, {
  style: "currency",
  currency: CURRENCY,
  maximumFractionDigits: 0,
});
const currencyCompact = new Intl.NumberFormat(LOCALE, {
  style: "currency",
  currency: CURRENCY,
  notation: "compact",
  minimumFractionDigits: 0,
  maximumFractionDigits: 1,
});
const integer = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 0 });
const compact = new Intl.NumberFormat(LOCALE, { notation: "compact", maximumFractionDigits: 1 });

function formatCurrency(value: number, opts: { compact?: boolean } = {}): string {
  return opts.compact ? currencyCompact.format(value) : currencyFull.format(value);
}

export function formatInteger(value: number, opts: { compact?: boolean } = {}): string {
  return opts.compact ? compact.format(value) : integer.format(value);
}

/** 0.1234 → "12.3%"; with `signed`, positive values get a "+". */
export function formatPercent(
  fraction: number,
  opts: { signed?: boolean; digits?: number } = {},
): string {
  const digits = opts.digits ?? 1;
  const value = (fraction * 100).toFixed(digits);
  const sign = opts.signed && fraction > 0 ? "+" : "";
  // Avoid "-0.0%".
  return `${sign}${Number(value) === 0 ? (0).toFixed(digits) : value}%`;
}

export function formatValue(
  value: number,
  format: ValueFormat,
  opts: { compact?: boolean } = {},
): string {
  switch (format) {
    case "currency":
      return formatCurrency(value, opts);
    case "percent":
      return formatPercent(value);
    case "integer":
      return formatInteger(value, opts);
    case "number":
      return opts.compact
        ? compact.format(value)
        : new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 2 }).format(value);
  }
}

const monthShort = new Intl.DateTimeFormat(LOCALE, { month: "short", timeZone: "UTC" });
const monthYear = new Intl.DateTimeFormat(LOCALE, {
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});

/** "2026-10" → "Oct" (or "Oct 2026" with `withYear`). */
export function formatMonth(isoMonth: string, opts: { withYear?: boolean } = {}): string {
  const date = new Date(`${isoMonth}-01T00:00:00Z`);
  return (opts.withYear ? monthYear : monthShort).format(date);
}

const dateFmt = new Intl.DateTimeFormat(LOCALE, {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: TIME_ZONE,
});
const dateTimeFmt = new Intl.DateTimeFormat(LOCALE, {
  day: "numeric",
  month: "short",
  hour: "numeric",
  minute: "2-digit",
  timeZone: TIME_ZONE,
});

export function formatDate(iso: string): string {
  return dateFmt.format(new Date(iso));
}

export function formatDateTime(iso: string): string {
  return dateTimeFmt.format(new Date(iso));
}

/** Relative time against a fixed "now" (injectable for deterministic rendering/tests). */
export function formatRelative(iso: string, now: Date): string {
  const seconds = Math.round((now.getTime() - new Date(iso).getTime()) / 1000);
  if (seconds < 45) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  if (days === 1) return "yesterday";
  if (days < 7) return `${days} days ago`;
  return formatDate(iso);
}

export function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms} ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)} s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes} m ${Math.round(seconds % 60)} s`;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value < 10 ? 1 : 0)} ${units[unit]}`;
}
