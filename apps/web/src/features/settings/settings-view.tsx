"use client";

import { useState, type FormEvent, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Field, Input, Select, Switch } from "@/components/ui/field";
import { PageHeader } from "@/components/ui/layout";
import { Notice } from "@/components/ui/states";
import { useToast } from "@/components/ui/toast";
import { SystemStatusPanel } from "@/features/system-status/system-status-panel";
import { cn } from "@/lib/cn";
import { formatBytes, formatInteger, formatPercent } from "@/lib/format";
import type { UsageSummary, UserSettings } from "@/types/domain";

const SECTIONS = [
  { id: "profile", label: "Profile" },
  { id: "analysis", label: "Analysis" },
  { id: "privacy", label: "Data & privacy" },
  { id: "usage", label: "Usage" },
  { id: "system", label: "System status" },
  { id: "danger", label: "Danger zone" },
] as const;

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

function Meter({
  label,
  value,
  max,
  display,
}: {
  label: string;
  value: number;
  max: number;
  display: string;
}) {
  const ratio = Math.min(1, value / max);
  return (
    <div>
      <div className="flex items-baseline justify-between text-[13px]">
        <span className="text-ink">{label}</span>
        <span className="text-ink-2 tabular">{display}</span>
      </div>
      <div
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-valuenow={value}
        className="mt-2 h-1.5 overflow-hidden rounded-full bg-warm-300/70"
      >
        <div
          className={cn("h-full rounded-full", ratio > 0.85 ? "bg-amber" : "bg-forest")}
          style={{ width: `${Math.max(2, ratio * 100)}%` }}
        />
      </div>
    </div>
  );
}

export function SettingsView({ initial, usage }: { initial: UserSettings; usage: UsageSummary }) {
  const [settings, setSettings] = useState(initial);
  const [errors, setErrors] = useState<Partial<Record<"fullName" | "email", string>>>({});
  const [confirm, setConfirm] = useState("");
  const { notify } = useToast();
  const set = <K extends keyof UserSettings>(key: K, value: UserSettings[K]) =>
    setSettings((s) => ({ ...s, [key]: value }));

  function saveProfile(event: FormEvent) {
    event.preventDefault();
    const next: typeof errors = {};
    if (settings.fullName.trim().length < 2) next.fullName = "Enter your full name.";
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(settings.email))
      next.email = "Enter a valid email address.";
    setErrors(next);
    if (Object.keys(next).length === 0)
      notify({
        tone: "success",
        title: "Profile updated",
        description: "Demo: changes are kept for this session only.",
      });
  }

  return (
    <>
      <PageHeader
        eyebrow="Account"
        title="Settings"
        description="Your profile, how the analyst behaves, and how your data is handled."
      />

      <div className="mt-8 grid gap-10 xl:grid-cols-[180px_minmax(0,1fr)]">
        <nav aria-label="Settings sections" className="hidden xl:block">
          <ul className="sticky top-8 grid gap-0.5 text-[13px]">
            {SECTIONS.map((s) => (
              <li key={s.id}>
                <a
                  href={`#${s.id}`}
                  className="block rounded-sm px-2.5 py-1.5 text-ink-2 hover:bg-warm-200 hover:text-ink"
                >
                  {s.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        <div className="min-w-0">
          <SettingsSection
            id="profile"
            title="Profile"
            description="How you appear on reports and in history."
          >
            <form onSubmit={saveProfile} className="grid max-w-xl gap-4" noValidate>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Full name" error={errors.fullName}>
                  {({ id, describedBy, invalid }) => (
                    <Input
                      id={id}
                      aria-describedby={describedBy}
                      aria-invalid={invalid}
                      value={settings.fullName}
                      onChange={(e) => set("fullName", e.target.value)}
                    />
                  )}
                </Field>
                <Field label="Role">
                  {({ id }) => (
                    <Input
                      id={id}
                      value={settings.role}
                      onChange={(e) => set("role", e.target.value)}
                    />
                  )}
                </Field>
              </div>
              <Field label="Email" error={errors.email} hint="Used to sign in.">
                {({ id, describedBy, invalid }) => (
                  <Input
                    id={id}
                    type="email"
                    aria-describedby={describedBy}
                    aria-invalid={invalid}
                    value={settings.email}
                    onChange={(e) => set("email", e.target.value)}
                  />
                )}
              </Field>
              <Field label="Timezone">
                {({ id }) => (
                  <Select
                    id={id}
                    value={settings.timezone}
                    onChange={(e) => set("timezone", e.target.value)}
                    className="w-full"
                  >
                    {[
                      "Asia/Kolkata",
                      "Europe/London",
                      "America/New_York",
                      "America/Los_Angeles",
                      "UTC",
                    ].map((tz) => (
                      <option key={tz}>{tz}</option>
                    ))}
                  </Select>
                )}
              </Field>
              <div>
                <Button type="submit" variant="primary">
                  Save profile
                </Button>
              </div>
            </form>
          </SettingsSection>

          <SettingsSection
            id="analysis"
            title="Analysis"
            description="Defaults the agent uses for every question."
          >
            <div className="grid max-w-xl gap-6">
              <fieldset>
                <legend className="text-sm font-medium text-ink">
                  When a question is ambiguous
                </legend>
                <div className="mt-3 grid gap-2">
                  {(
                    [
                      [
                        "ask",
                        "Ask me to clarify",
                        "The run pauses with a short question and options.",
                      ],
                      [
                        "assume",
                        "Make a reasonable assumption",
                        "The assumption is shown at the top of the answer.",
                      ],
                    ] as const
                  ).map(([value, label, help]) => (
                    <label
                      key={value}
                      className={cn(
                        "flex cursor-pointer items-start gap-3 rounded-sm border px-3.5 py-3 transition-colors",
                        settings.clarificationMode === value
                          ? "border-forest bg-forest-50/50"
                          : "border-line bg-paper hover:border-line-strong",
                      )}
                    >
                      <input
                        type="radio"
                        name="clarification"
                        value={value}
                        checked={settings.clarificationMode === value}
                        onChange={() => set("clarificationMode", value)}
                        className="mt-1 accent-[var(--color-forest)]"
                      />
                      <span>
                        <span className="block text-sm font-medium text-ink">{label}</span>
                        <span className="block text-[13px] text-ink-2">{help}</span>
                      </span>
                    </label>
                  ))}
                </div>
              </fieldset>
              <Field
                label="Rows shown per result"
                hint="Up to 10,000 rows are fetched; this controls the default view."
              >
                {({ id, describedBy }) => (
                  <Select
                    id={id}
                    aria-describedby={describedBy}
                    value={settings.defaultRowLimit}
                    onChange={(e) => set("defaultRowLimit", Number(e.target.value))}
                    className="w-48"
                  >
                    {[100, 500, 1000, 5000].map((n) => (
                      <option key={n} value={n}>
                        {formatInteger(n)} rows
                      </option>
                    ))}
                  </Select>
                )}
              </Field>
              <Switch
                checked={settings.autoCharts}
                onChange={(v) => set("autoCharts", v)}
                label="Create charts automatically"
                description="Choose a chart when the result suits one."
              />
              <Switch
                checked={settings.showSqlByDefault}
                onChange={(v) => set("showSqlByDefault", v)}
                label="Open the SQL tab by default"
                description="Useful if you review every query."
              />
              <div>
                <Button
                  variant="secondary"
                  onClick={() => notify({ tone: "success", title: "Analysis preferences saved" })}
                >
                  Save preferences
                </Button>
              </div>
            </div>
          </SettingsSection>

          <SettingsSection
            id="privacy"
            title="Data & privacy"
            description="What the language model can and cannot see."
          >
            <div className="grid max-w-xl gap-5">
              <Switch
                checked={settings.maskSensitiveColumns}
                onChange={(v) => set("maskSensitiveColumns", v)}
                label="Mask sensitive columns"
                description="Columns marked sensitive (such as email) never have sample values sent to the model."
              />
              <Notice tone="info" title="What the model receives">
                Table and column names, types, column profiles, at most 50 result rows per query and
                computed facts. Full tables are never sent, and all queries run read-only.
              </Notice>
              <p className="text-[13px] text-ink-2">
                Query results are kept for 30 days unless they’re part of a report or a pinned
                chart.
              </p>
            </div>
          </SettingsSection>

          <SettingsSection
            id="usage"
            title="Usage"
            description="Limits reset daily (runs) and monthly (tokens)."
          >
            <div className="grid max-w-xl gap-5">
              <Meter
                label="Analyses today"
                value={usage.runsToday}
                max={usage.runsLimit}
                display={`${usage.runsToday} of ${usage.runsLimit}`}
              />
              <Meter
                label="Model tokens this month"
                value={usage.tokensMonth}
                max={usage.tokensLimit}
                display={`${formatInteger(usage.tokensMonth, { compact: true })} of ${formatInteger(usage.tokensLimit, { compact: true })} · ${formatPercent(usage.tokensMonth / usage.tokensLimit, { digits: 0 })}`}
              />
              <Meter
                label="Dataset storage"
                value={usage.storageBytes}
                max={usage.storageLimitBytes}
                display={`${formatBytes(usage.storageBytes)} of ${formatBytes(usage.storageLimitBytes)} · ${usage.datasets} datasets`}
              />
            </div>
          </SettingsSection>

          <SettingsSection
            id="system"
            title="System status"
            description="Live connectivity check between this app, the API and the database."
          >
            <SystemStatusPanel embedded />
          </SettingsSection>

          <SettingsSection id="danger" title="Danger zone" description="Permanent actions.">
            <div className="max-w-xl rounded-md border border-rust/30 bg-paper p-5">
              <h3 className="text-sm font-semibold text-ink">Delete account and data</h3>
              <p className="mt-1 text-[13px] leading-5 text-ink-2">
                Removes your datasets, analyses, reports and pinned charts. This can’t be undone.
              </p>
              <Field label='Type "delete" to confirm' className="mt-4">
                {({ id }) => (
                  <Input
                    id={id}
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value)}
                    autoComplete="off"
                  />
                )}
              </Field>
              <Button
                variant="danger"
                className="mt-4"
                disabled={confirm !== "delete"}
                onClick={() => {
                  setConfirm("");
                  notify({
                    tone: "info",
                    title: "Nothing was deleted",
                    description: "Account deletion needs the backend (a later phase).",
                  });
                }}
              >
                Delete account
              </Button>
            </div>
          </SettingsSection>
        </div>
      </div>
    </>
  );
}
