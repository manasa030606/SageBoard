"use client";

import { ChevronDown, Eye, EyeOff } from "lucide-react";
import type { ComponentProps, ReactNode } from "react";
import { useId, useState } from "react";

import { cn } from "@/lib/cn";

const control =
  "w-full rounded-sm border border-line-strong bg-paper text-sm text-ink transition-[border-color,box-shadow] duration-150 " +
  "hover:border-ink-3 focus:border-forest focus:outline-none focus:ring-2 focus:ring-forest/20 " +
  "disabled:cursor-not-allowed disabled:bg-warm-200 disabled:text-ink-3 aria-[invalid=true]:border-rust";

export function Input({ className, ...props }: ComponentProps<"input">) {
  return <input className={cn(control, "h-9 px-3", className)} {...props} />;
}

/**
 * Password input with a show/hide button inside its right edge. Hidden by default. The
 * button keeps the focus where it was (mouse press doesn't take it from the input), and its
 * label says what it does now ("Show characters" / "Hide characters"). It avoids the word
 * "password" on purpose: a label search for the field by that word must still find one element.
 */
export function PasswordInput({ className, ...props }: Omit<ComponentProps<"input">, "type">) {
  const [visible, setVisible] = useState(false);
  const Icon = visible ? EyeOff : Eye;
  return (
    <span className="relative block">
      <Input {...props} type={visible ? "text" : "password"} className={cn("pr-10", className)} />
      <button
        type="button"
        aria-label={visible ? "Hide characters" : "Show characters"}
        aria-pressed={visible}
        aria-controls={props.id}
        onMouseDown={(event) => event.preventDefault()}
        onClick={() => setVisible((v) => !v)}
        className="absolute inset-y-0 right-0 grid w-10 place-items-center rounded-r-sm text-ink-3 transition-colors hover:text-ink focus-visible:text-ink focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-forest"
      >
        <Icon className="size-4" aria-hidden strokeWidth={1.75} />
      </button>
    </span>
  );
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
