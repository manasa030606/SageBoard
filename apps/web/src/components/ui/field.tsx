"use client";

import { ChevronDown } from "lucide-react";
import type { ComponentProps, ReactNode } from "react";
import { useId } from "react";

import { cn } from "@/lib/cn";

const control =
  "w-full rounded-sm border border-line-strong bg-paper text-sm text-ink transition-[border-color,box-shadow] duration-150 " +
  "hover:border-ink-3 focus:border-forest focus:outline-none focus:ring-2 focus:ring-forest/20 " +
  "disabled:cursor-not-allowed disabled:bg-warm-200 disabled:text-ink-3 aria-[invalid=true]:border-rust";

export function Input({ className, ...props }: ComponentProps<"input">) {
  return <input className={cn(control, "h-9 px-3", className)} {...props} />;
}

export function Select({
  className,
  children,
  size = "md",
  ...props
}: Omit<ComponentProps<"select">, "size"> & { size?: "sm" | "md" }) {
  return (
    <span className={cn("relative inline-flex", className?.includes("w-full") && "w-full")}>
      <select
        className={cn(
          control,
          "appearance-none pr-8 pl-3",
          size === "sm" ? "h-8 text-[13px]" : "h-9",
          className,
        )}
        {...props}
      >
        {children}
      </select>
      <ChevronDown
        aria-hidden
        className="pointer-events-none absolute top-1/2 right-2.5 size-3.5 -translate-y-1/2 text-ink-3"
      />
    </span>
  );
}

/** Label + control + hint/error, wired with ids for screen readers. */
export function Field({
  label,
  hint,
  error,
  children,
  className,
}: {
  label: string;
  hint?: string;
  error?: string;
  className?: string;
  children: (ids: { id: string; describedBy?: string; invalid: boolean }) => ReactNode;
}) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;
  return (
    <div className={cn("grid gap-1.5", className)}>
      <label htmlFor={id} className="text-[13px] font-medium text-ink">
        {label}
      </label>
      {children({ id, describedBy, invalid: Boolean(error) })}
      {hint && !error ? (
        <p id={hintId} className="text-xs text-ink-2">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={errorId} className="text-xs text-rust">
          {error}
        </p>
      ) : null}
    </div>
  );
}
