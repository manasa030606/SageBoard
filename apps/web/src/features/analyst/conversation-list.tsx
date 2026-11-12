"use client";

import { MessageSquarePlus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import { formatRelative } from "@/lib/format";
import type { Dataset } from "@/types/domain";

import type { WorkspaceConversation } from "./workspace-state";

export function ConversationList({
  conversations,
  activeId,
  datasets,
  now,
  onSelect,
  onNew,
}: {
  conversations: WorkspaceConversation[];
  activeId: string | null;
  datasets: readonly Dataset[];
  now: Date;
  onSelect: (id: string) => void;
  onNew: () => void;
}) {
  const today = now.toISOString().slice(0, 10);
  const groups = [
    { label: "Today", items: conversations.filter((c) => c.updatedAt.slice(0, 10) === today) },
    { label: "Earlier", items: conversations.filter((c) => c.updatedAt.slice(0, 10) !== today) },
  ].filter((g) => g.items.length > 0);
  const datasetName = (id: string) => datasets.find((d) => d.id === id)?.name ?? "Dataset";

  return (
    <div className="flex h-full flex-col">
      <div className="px-3 pt-4 pb-3">
        <Button
          variant="secondary"
          className="w-full justify-start"
          onClick={onNew}
          leadingIcon={<MessageSquarePlus className="size-4 text-forest" aria-hidden />}
        >
          New analysis
        </Button>
      </div>
      <nav aria-label="Conversations" className="min-h-0 flex-1 overflow-y-auto px-2 pb-4">
        {groups.map((group) => (
          <div key={group.label} className="mt-3 first:mt-0">
            <p className="px-2.5 pb-1.5 eyebrow">{group.label}</p>
            <ul className="grid gap-px">
              {group.items.map((c) => {
                const active = c.id === activeId;
                return (
                  <li key={c.id}>
                    <button
                      type="button"
                      onClick={() => onSelect(c.id)}
                      aria-current={active ? "true" : undefined}
                      className={cn(
                        "grid w-full gap-0.5 rounded-sm px-2.5 py-2 text-left transition-colors duration-100",
                        active
                          ? "bg-paper shadow-[0_0_0_1px_var(--color-line)]"
                          : "hover:bg-warm-300/50",
                      )}
                    >
                      <span
                        className={cn(
                          "truncate text-[13px]",
                          active ? "font-medium text-ink" : "text-ink",
                        )}
                      >
                        {c.title}
                      </span>
                      <span className="truncate text-2xs text-ink-2">
                        {datasetName(c.datasetId)} ·{" "}
                        {c.isNew ? "now" : formatRelative(c.updatedAt, now)}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>
    </div>
  );
}
