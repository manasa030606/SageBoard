"use client";

import { useId, useRef, type KeyboardEvent, type ReactNode } from "react";

import { cn } from "@/lib/cn";

export interface TabItem<K extends string> {
  key: K;
  label: ReactNode;
  count?: number;
}

/**
 * Accessible tabs (WAI-ARIA pattern): arrow keys move between tabs, Home/End jump,
 * only the active tab is in the tab order. The caller renders the active panel via
 * `renderPanel` so content lives next to its own state.
 */
export function Tabs<K extends string>({
  items,
  value,
  onChange,
  renderPanel,
  label,
  className,
  size = "md",
}: {
  items: TabItem<K>[];
  value: K;
  onChange: (key: K) => void;
  renderPanel: (key: K) => ReactNode;
  label: string;
  className?: string;
  size?: "sm" | "md";
}) {
  const baseId = useId();
  const refs = useRef<Array<HTMLButtonElement | null>>([]);

  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const last = items.length - 1;
    const next =
      event.key === "ArrowRight"
        ? index === last
          ? 0
          : index + 1
        : event.key === "ArrowLeft"
          ? index === 0
            ? last
            : index - 1
          : event.key === "Home"
            ? 0
            : event.key === "End"
              ? last
              : null;
    if (next === null) return;
    event.preventDefault();
    const item = items[next];
    if (!item) return;
    onChange(item.key);
    refs.current[next]?.focus();
  }

  return (
    <div className={className}>
      <div role="tablist" aria-label={label} className="flex gap-1 border-b border-line">
        {items.map((item, index) => {
          const selected = item.key === value;
          return (
            <button
              key={item.key}
              ref={(el) => {
                refs.current[index] = el;
              }}
              id={`${baseId}-tab-${item.key}`}
              role="tab"
              type="button"
              aria-selected={selected}
              aria-controls={`${baseId}-panel-${item.key}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => onChange(item.key)}
              onKeyDown={(e) => onKeyDown(e, index)}
              className={cn(
                "-mb-px inline-flex items-center gap-1.5 border-b-2 px-2.5 font-medium transition-colors duration-150",
                size === "sm" ? "h-8 text-[13px]" : "h-9 text-sm",
                selected
                  ? "border-forest text-ink"
                  : "border-transparent text-ink-2 hover:text-ink",
              )}
            >
              {item.label}
              {item.count !== undefined ? (
                <span className="rounded-xs bg-warm-200 px-1 text-2xs text-ink-2 tabular">
                  {item.count}
                </span>
              ) : null}
            </button>
          );
        })}
      </div>
      <div
        role="tabpanel"
        id={`${baseId}-panel-${value}`}
        aria-labelledby={`${baseId}-tab-${value}`}
        tabIndex={0}
        className="focus-visible:outline-offset-4"
      >
        {renderPanel(value)}
      </div>
    </div>
  );
}

/** Compact segmented control for switching views (e.g. chart vs table). */
export function Segmented<K extends string>({
  options,
  value,
  onChange,
  label,
}: {
  options: { key: K; label: string }[];
  value: K;
  onChange: (key: K) => void;
  label: string;
}) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className="inline-flex rounded-sm border border-line bg-warm-200/60 p-0.5"
    >
      {options.map((option) => {
        const checked = option.key === value;
        return (
          <button
            key={option.key}
            type="button"
            role="radio"
            aria-checked={checked}
            onClick={() => onChange(option.key)}
            className={cn(
              "h-6 rounded-xs px-2 text-xs font-medium transition-colors duration-150",
              checked
                ? "bg-paper text-ink shadow-[0_0_0_1px_var(--color-line)]"
                : "text-ink-2 hover:text-ink",
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
