import { cn } from "@/lib/cn";

/** Sageboard mark: a board with three rising bars, the last one in sage. */
export function LogoMark({
  className,
  inverted = false,
}: {
  className?: string;
  inverted?: boolean;
}) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden className={cn("size-6 shrink-0", className)}>
      <rect
        width="24"
        height="24"
        rx="5"
        fill={inverted ? "var(--color-warm)" : "var(--color-forest)"}
      />
      <rect
        x="6"
        y="12"
        width="3"
        height="6"
        rx="0.75"
        fill={inverted ? "var(--color-forest)" : "var(--color-warm)"}
      />
      <rect
        x="10.5"
        y="9"
        width="3"
        height="9"
        rx="0.75"
        fill={inverted ? "var(--color-forest)" : "var(--color-warm)"}
      />
      <rect x="15" y="6" width="3" height="12" rx="0.75" fill="var(--color-sage)" />
    </svg>
  );
}

export function Logo({ className, inverted = false }: { className?: string; inverted?: boolean }) {
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <LogoMark inverted={inverted} />
      <span
        className={cn("text-title text-[19px] leading-none", inverted ? "text-warm" : "text-navy")}
      >
        Sageboard
      </span>
    </span>
  );
}
