"use client";

import { MessageSquarePlus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import { formatRelative } from "@/lib/format";

export interface ConversationItem {
  id: string;
  title: string;
  updatedAt: string;
}

export function ConversationList({
  conversations,
  activeId,
  onSelect,
  onNew,
}: {
  conversations: ConversationItem[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
}) {
  const now = new Date();
  const today = now.toISOString().slice(0, 10);
  const groups = [
    { label: "Today", items: conversations.filter((c) => c.updatedAt.slice(0, 10) === today) },
    { label: "Earlier", items: conversations.filter((c) => c.updatedAt.slice(0, 10) !== today) },
  ].filter((g) => g.items.length > 0);

  return (
    <div className="flex h-full flex-col">
      <div className="px-3 pt-4 pb-3">
        <Button
          variant="secondary"
          className="w-full justify-start"
          onClick={onNew}
          leadingIcon={<MessageSquarePlus className="size-4" aria-hidden />}
        >
          New conversation
        </Button>
      </div>
      <nav aria-label="Conversations" className="min-h-0 flex-1 overflow-y-auto px-3 pb-4">
        {groups.length === 0 ? (
          <p className="px-2 pt-2 text-[13px] leading-5 text-ink-2">
            Conversations with the analyst appear here.
          </p>
        ) : (
          groups.map((group) => (
            <div key={group.label} className="mb-4">
              <p className="px-2 pb-1.5 eyebrow">{group.label}</p>
              <ul className="grid gap-0.5">
                {group.items.map((conversation) => (
                  <li key={conversation.id}>
                    <button
                      type="button"
                      onClick={() => onSelect(conversation.id)}
                      aria-current={conversation.id === activeId ? "true" : undefined}
                      className={cn(
                        "grid w-full gap-0.5 rounded-sm px-2 py-2 text-left transition-colors",
                        conversation.id === activeId
                          ? "bg-sage-100 text-ink"
                          : "text-ink-2 hover:bg-warm-300/60 hover:text-ink",
                      )}
                    >
                      <span className="truncate text-[13px] font-medium">{conversation.title}</span>
                      <span className="text-2xs text-ink-3">
                        {formatRelative(conversation.updatedAt, now)}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))
        )}
      </nav>
    </div>
  );
}
