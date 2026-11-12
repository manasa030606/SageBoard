import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

/** Top of every app page: eyebrow, serif title, description and actions. */
export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  className,
}: {
  eyebrow?: string;
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <header className={cn("flex flex-wrap items-end justify-between gap-x-8 gap-y-4", className)}>
      <div className="min-w-0">
        {eyebrow ? <p className="mb-2 eyebrow">{eyebrow}</p> : null}
        <h1 className="text-title text-[28px] text-ink sm:text-[32px]">{title}</h1>
        {description ? (
          <p className="mt-2 max-w-2xl text-[15px] leading-6 text-ink-2">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
  );
}

/**
 * A titled region separated by a hairline rule rather than a card. Use `surface`
 * only when content (tables, charts) needs a white ground.
 */
export function Section({
  title,
  description,
  actions,
  children,
  surface = false,
  className,
  bodyClassName,
  id,
}: {
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  surface?: boolean;
  className?: string;
  bodyClassName?: string;
  id?: string;
}) {
  const headingId = id ? `${id}-heading` : undefined;
  return (
    <section aria-labelledby={headingId} className={cn("flex min-w-0 flex-col", className)} id={id}>
      {title || actions ? (
        <div className="mb-3 flex items-end justify-between gap-4">
          <div className="min-w-0">
            {title ? (
              <h2 id={headingId} className="text-[15px] font-semibold text-ink">
                {title}
              </h2>
            ) : null}
            {description ? <p className="mt-0.5 text-[13px] text-ink-2">{description}</p> : null}
          </div>
          {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
        </div>
      ) : null}
      <div
        className={cn("flex-1", surface && "rounded-md border border-line bg-paper", bodyClassName)}
      >
        {children}
      </div>
    </section>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="inline-flex h-5 min-w-5 items-center justify-center rounded-xs border border-line bg-paper px-1 text-2xs text-ink-2">
      {children}
    </kbd>
  );
}
