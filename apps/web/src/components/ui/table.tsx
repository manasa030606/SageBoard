import type { ComponentProps, ReactNode } from "react";

import { cn } from "@/lib/cn";

/** Table primitives with consistent density, alignment and hover treatment. */
export function Table({ className, ...props }: ComponentProps<"table">) {
  return (
    <div className="w-full overflow-x-auto">
      <table className={cn("w-full border-collapse text-left text-[13px]", className)} {...props} />
    </div>
  );
}

export function THead({ className, ...props }: ComponentProps<"thead">) {
  return <thead className={cn("border-b border-line bg-warm/60", className)} {...props} />;
}

export function TH({
  className,
  align = "left",
  ...props
}: ComponentProps<"th"> & { align?: "left" | "right" }) {
  return (
    <th
      scope="col"
      className={cn(
        "h-9 px-4 text-2xs font-medium tracking-[0.06em] whitespace-nowrap text-ink-2 uppercase",
        align === "right" && "text-right",
        className,
      )}
      {...props}
    />
  );
}

export function TR({
  className,
  interactive,
  ...props
}: ComponentProps<"tr"> & { interactive?: boolean }) {
  return (
    <tr
      className={cn(
        "border-b border-line/70 last:border-0",
        interactive &&
          "cursor-pointer transition-colors duration-100 focus-within:bg-sage-50 hover:bg-sage-50",
        className,
      )}
      {...props}
    />
  );
}

export function TD({
  className,
  align = "left",
  numeric,
  ...props
}: ComponentProps<"td"> & { align?: "left" | "right"; numeric?: boolean }) {
  return (
    <td
      className={cn(
        "h-11 px-4 align-middle text-ink",
        (align === "right" || numeric) && "text-right",
        numeric && "font-mono text-[12.5px] tabular",
        className,
      )}
      {...props}
    />
  );
}

/** Horizontal proportion bar used inside table cells. */
export function InlineBar({
  value,
  max,
  tone = "forest",
}: {
  value: number;
  max: number;
  tone?: "forest" | "amber" | "navy";
}) {
  const pct = max > 0 ? Math.max(2, Math.round((value / max) * 100)) : 0;
  const fill = { forest: "bg-forest", amber: "bg-amber", navy: "bg-navy" }[tone];
  return (
    <div aria-hidden className="h-1.5 w-full rounded-full bg-warm-300/70">
      <div className={cn("h-full rounded-full", fill)} style={{ width: `${pct}%` }} />
    </div>
  );
}

export function TableCaption({ children }: { children: ReactNode }) {
  return <caption className="sr-only">{children}</caption>;
}
