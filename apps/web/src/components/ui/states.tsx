import type { ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Info, XCircle } from "lucide-react";

import { cn } from "@/lib/cn";

/** Shimmer-free skeleton: a calm, static placeholder block. */
export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn("animate-pulse rounded-xs bg-warm-300/70", className)} />;
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: {
  icon?: ReactNode;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center px-6 py-14 text-center", className)}>
      {icon ? (
        <div className="mb-4 grid size-10 place-items-center rounded-sm border border-line bg-paper text-ink-2">
          {icon}
        </div>
      ) : null}
      <h3 className="text-[15px] font-semibold text-ink">{title}</h3>
      {description ? (
        <p className="mt-1.5 max-w-sm text-sm leading-6 text-ink-2">{description}</p>
      ) : null}
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}

export function ErrorState({
  title = "Something went wrong",
  description,
  action,
  code,
}: {
  title?: string;
  description: ReactNode;
  action?: ReactNode;
  code?: string;
}) {
  return (
    <div role="alert" className="flex flex-col items-center px-6 py-14 text-center">
      <div className="mb-4 grid size-10 place-items-center rounded-sm border border-rust/30 bg-rust-50 text-rust">
        <XCircle className="size-5" aria-hidden />
      </div>
      <h3 className="text-[15px] font-semibold text-ink">{title}</h3>
      <p className="mt-1.5 max-w-md text-sm leading-6 text-ink-2">{description}</p>
      {code ? <code className="mt-2 text-2xs text-ink-3">{code}</code> : null}
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}

type NoticeTone = "info" | "success" | "warning" | "error";

const noticeStyles: Record<NoticeTone, { box: string; icon: ReactNode }> = {
  info: {
    box: "border-sage-600/40 bg-sage-50 text-navy",
    icon: <Info className="size-4" aria-hidden />,
  },
  success: {
    box: "border-forest/30 bg-forest-50 text-forest",
    icon: <CheckCircle2 className="size-4" aria-hidden />,
  },
  warning: {
    box: "border-amber/50 bg-amber-100 text-amber-ink",
    icon: <AlertTriangle className="size-4" aria-hidden />,
  },
  error: {
    box: "border-rust/30 bg-rust-50 text-rust",
    icon: <XCircle className="size-4" aria-hidden />,
  },
};

/** Inline message inside a page or panel (not a toast). */
export function Notice({
  tone = "info",
  title,
  children,
  action,
  className,
}: {
  tone?: NoticeTone;
  title?: string;
  children?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  const style = noticeStyles[tone];
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={cn(
        "flex items-start gap-3 rounded-sm border px-3.5 py-3 text-[13px] leading-5",
        style.box,
        className,
      )}
    >
      <span className="mt-0.5 shrink-0">{style.icon}</span>
      <div className="min-w-0 flex-1">
        {title ? <p className="font-semibold">{title}</p> : null}
        {children ? (
          <div className={cn(title && "mt-0.5", "text-ink-2 [&_strong]:text-ink")}>{children}</div>
        ) : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}
