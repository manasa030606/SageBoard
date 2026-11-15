/*
 * Histogram binning (pure, unit-tested). The agent's histogram spec names one numeric
 * column; the frontend bins its values into equal-width intervals.
 */

export interface HistogramBin {
  /** Interval label, e.g. "120–140". */
  bin: string;
  count: number;
}

const MAX_BINS = 12;

/** Round a step up to a friendly size: 1/2/2.5/5 × 10^k. */
function niceStep(raw: number): number {
  if (!Number.isFinite(raw) || raw <= 0) return 1;
  const power = Math.floor(Math.log10(raw));
  const base = raw / 10 ** power;
  const nice = base <= 1 ? 1 : base <= 2 ? 2 : base <= 2.5 ? 2.5 : base <= 5 ? 5 : 10;
  return nice * 10 ** power;
}

const short = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });

function label(value: number): string {
  return Math.abs(value) >= 10_000 ? short.format(value) : String(Number(value.toFixed(2)));
}

export function binValues(values: unknown[], maxBins: number = MAX_BINS): HistogramBin[] {
  const numbers = values
    .map((v) => (typeof v === "string" ? Number(v) : v))
    .filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  if (numbers.length === 0) return [];
  const min = Math.min(...numbers);
  const max = Math.max(...numbers);
  if (min === max) return [{ bin: label(min), count: numbers.length }];
  const step = niceStep((max - min) / maxBins);
  const start = Math.floor(min / step) * step;
  const binCount = Math.max(1, Math.ceil((max - start) / step + 1e-9));
  const counts = new Array<number>(binCount).fill(0);
  for (const n of numbers) {
    const index = Math.min(binCount - 1, Math.floor((n - start) / step));
    counts[index] = (counts[index] ?? 0) + 1;
  }
  return counts.map((count, i) => ({
    bin: `${label(start + i * step)}–${label(start + (i + 1) * step)}`,
    count,
  }));
}
