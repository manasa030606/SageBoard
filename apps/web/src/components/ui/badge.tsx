import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export type Tone = "neutral" | "positive" | "warning" | "critical" | "info" | "accent";

const tones: Record<Tone, string> = {
  neutral: "bg-warm-200 text-ink-2",
  positive: "bg-forest-50 text-forest",
  warning: "bg-amber-100 text-amber-ink",
  critical: "bg-rust-50 text-rust",
  info: "bg-sage-50 text-navy",
  accent: "bg-navy text-warm",
};

const dots: Record<Tone, string> = {
  neutral: "bg-ink-3",
  positive: "bg-forest",
  warning: "bg-amber",
  critical: "bg-rust",
  info: "bg-navy",
  accent: "bg-amber",
};

export function Badge({
  tone = "neutral",
  dot = false,
  className,
  children,
}: {
  tone?: Tone;
  dot?: boolean;
  className?: string;
  children: ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex h-5 items-center gap-1.5 rounded-xs px-1.5 text-2xs font-medium whitespace-nowrap",
        tones[tone],
        className,
      )}
    >
      {dot ? <span aria-hidden className={cn("size-1.5 rounded-full", dots[tone])} /> : null}
      {children}
    </span>
  );
}

/** A small round status indicator with an accessible label. */
export function StatusDot({ tone, label, pulse }: { tone: Tone; label: string; pulse?: boolean }) {
  return (
    <span className="inline-flex items-center gap-2 text-[13px] text-ink-2">
      <span
        aria-hidden
        className={cn("size-2 rounded-full", dots[tone], pulse && "animate-pulse")}
      />
      {label}
    </span>
  );
}
