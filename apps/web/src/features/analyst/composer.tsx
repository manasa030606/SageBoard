"use client";

import { ArrowUp } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { Kbd } from "@/components/ui/layout";
import { cn } from "@/lib/cn";

export function Composer({
  onSubmit,
  disabled,
  placeholder,
  disabledReason,
}: {
  onSubmit: (question: string) => void;
  disabled?: boolean;
  placeholder: string;
  disabledReason?: string;
}) {
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  // Auto-grow up to ~6 lines.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 168)}px`;
  }, [value]);

  function submit(event?: FormEvent) {
    event?.preventDefault();
    const question = value.trim();
    if (!question || disabled) return;
    onSubmit(question);
    setValue("");
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  }

  const canSend = value.trim().length > 0 && !disabled;

  return (
    <form onSubmit={submit} className="grid gap-1.5">
      <div
        className={cn(
          "flex items-end gap-2 rounded-md border bg-paper p-2 pl-3.5 transition-[border-color,box-shadow] duration-150",
          "border-line-strong focus-within:border-forest focus-within:ring-2 focus-within:ring-forest/15",
        )}
      >
        <label htmlFor="analyst-question" className="sr-only">
          Ask a question about your data
        </label>
        <textarea
          id="analyst-question"
          ref={ref}
          rows={1}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={placeholder}
          maxLength={2000}
          className="min-h-9 flex-1 resize-none bg-transparent py-1.5 text-[15px] leading-6 text-ink focus:outline-none"
        />
        <button
          type="submit"
          disabled={!canSend}
          aria-label="Ask"
          className={cn(
            "grid size-9 shrink-0 place-items-center rounded-sm transition-colors duration-150",
            canSend ? "bg-forest text-warm hover:bg-forest-700" : "bg-warm-300 text-ink-3",
          )}
        >
          <ArrowUp className="size-4" aria-hidden strokeWidth={2.25} />
        </button>
      </div>
      <p className="flex items-center justify-between gap-3 px-1 text-2xs text-ink-2">
        <span>
          {disabled && disabledReason
            ? disabledReason
            : "Answers use read-only queries on the selected dataset."}
        </span>
        <span className="hidden items-center gap-1 sm:inline-flex">
          <Kbd>Enter</Kbd> to ask · <Kbd>Shift</Kbd>+<Kbd>Enter</Kbd> new line
        </span>
      </p>
    </form>
  );
}
