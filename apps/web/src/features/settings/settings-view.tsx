"use client";

import type { ReactNode } from "react";

import { PageHeader } from "@/components/ui/layout";
import { Notice } from "@/components/ui/states";
import { useSession } from "@/features/auth/session";
import { SystemStatusPanel } from "@/features/system-status/system-status-panel";
import { formatDate } from "@/lib/format";

function SettingsSection({
  id,
  title,
  description,
  children,
}: {
  id: string;
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <section
      id={id}
      aria-labelledby={`${id}-title`}
      className="scroll-mt-8 border-t border-line py-9 first:border-t-0 first:pt-0"
    >
      <div className="grid gap-6 lg:grid-cols-[240px_minmax(0,1fr)]">
        <div>
          <h2 id={`${id}-title`} className="text-[15px] font-semibold text-ink">
            {title}
          </h2>
          <p className="mt-1 text-[13px] leading-5 text-ink-2">{description}</p>
        </div>
        <div className="min-w-0">{children}</div>
      </div>
    </section>
  );
}

export function SettingsView() {
  const { user } = useSession();

  return (
    <>
      <PageHeader
        eyebrow="Account"
        title="Settings"
        description="Your account, what the model can see, and whether the system is healthy."
      />
      <div className="mt-8">
        <SettingsSection
          id="account"
          title="Account"
          description="The account you are signed in as."
        >
          {user ? (
            <dl className="grid max-w-xl gap-4 text-sm">
              <div>
                <dt className="text-[13px] text-ink-2">Name</dt>
                <dd className="text-ink">{user.full_name}</dd>
              </div>
              <div>
                <dt className="text-[13px] text-ink-2">Email</dt>
                <dd className="text-ink">{user.email}</dd>
              </div>
              <div>
                <dt className="text-[13px] text-ink-2">Member since</dt>
                <dd className="text-ink">{formatDate(user.created_at)}</dd>
              </div>
            </dl>
          ) : null}
        </SettingsSection>

        <SettingsSection
          id="privacy"
          title="Data & privacy"
          description="What the language model can and cannot see."
        >
          <div className="max-w-xl">
            <Notice tone="info" title="How your data is protected">
              Generated queries run read-only and are checked before they reach the database.
              Columns marked sensitive, such as email addresses, are replaced with a placeholder
              before any result is sent to the model.
            </Notice>
          </div>
        </SettingsSection>

        <SettingsSection
          id="system"
          title="System status"
          description="Live connectivity check between this app, the API and the database."
        >
          <SystemStatusPanel embedded />
        </SettingsSection>
      </div>
    </>
  );
}
