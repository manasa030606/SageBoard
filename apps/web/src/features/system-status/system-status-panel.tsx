"use client";

import type { ReactNode } from "react";

import { API_BASE_URL } from "@/lib/env";

import { useSystemStatus, type ProbeState } from "./use-system-status";

type Tone = "ok" | "warn" | "error" | "pending";

const TONE_STYLES: Record<Tone, { dot: string; text: string; label: string }> = {
  ok: { dot: "bg-forest-600", text: "text-forest-700", label: "Operational" },
  warn: { dot: "bg-amber-600", text: "text-navy-800", label: "Degraded" },
  error: { dot: "bg-rust-700", text: "text-rust-700", label: "Unavailable" },
  pending: { dot: "bg-sage-300", text: "text-navy-400", label: "Checking" },
};

function StatusLabel({ tone, label }: { tone: Tone; label?: string }) {
  const style = TONE_STYLES[tone];
  return (
    <span className={`inline-flex items-center gap-2 text-sm font-medium ${style.text}`}>
      <span
        aria-hidden
        className={`size-2 rounded-full ${style.dot} ${tone === "pending" ? "animate-pulse" : ""}`}
      />
      {label ?? style.label}
    </span>
  );
}

function Row({
  name,
  meta,
  tone,
  label,
  detail,
}: {
  name: string;
  meta: string;
  tone: Tone;
  label?: string;
  detail?: ReactNode;
}) {
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-x-6 gap-y-1 border-t border-sage-200 px-5 py-4 first:border-t-0 sm:grid-cols-[13rem_minmax(0,1fr)_auto]">
      <div className="col-start-1 row-start-1">
        <div className="text-sm font-medium text-navy-950">{name}</div>
        <div className="font-mono text-2xs text-navy-400">{meta}</div>
      </div>
      <div className="col-span-2 col-start-1 row-start-2 text-sm text-navy-600 sm:col-span-1 sm:col-start-2 sm:row-start-1">
        {detail}
      </div>
      <div className="col-start-2 row-start-1 justify-self-end sm:col-start-3">
        <StatusLabel tone={tone} label={label} />
      </div>
    </div>
  );
}

function probeTone<T>(probe: ProbeState<T>, ok: (data: T) => boolean = () => true): Tone {
  if (probe.kind === "loading") return "pending";
  if (probe.kind === "error") return "error";
  return ok(probe.data) ? "ok" : "warn";
}

function ErrorDetail({ probe }: { probe: ProbeState<unknown> }) {
  if (probe.kind !== "error") return null;
  return (
    <span>
      {probe.error.message}{" "}
      <code className="font-mono text-2xs text-navy-400">{probe.error.code}</code>
    </span>
  );
}

function Latency({ ms }: { ms: number }) {
  return <span className="tabular font-mono text-2xs text-navy-400">{ms} ms</span>;
}

export function SystemStatusPanel() {
  const { web, liveness, readiness, checkedAt, refresh } = useSystemStatus();
  const busy = [web, liveness, readiness].some((p) => p.kind === "loading");
  const checks = readiness.kind === "success" ? Object.entries(readiness.data.checks) : [];

  return (
    <section aria-labelledby="status-heading" className="w-full max-w-3xl">
      <header className="mb-6 flex items-end justify-between gap-4">
        <div>
          <p className="font-mono text-2xs tracking-[0.14em] text-navy-400 uppercase">
            Phase 1 · Foundation
          </p>
          <h1
            id="status-heading"
            className="mt-1 text-2xl font-semibold tracking-tight text-navy-950"
          >
            System status
          </h1>
        </div>
        <button
          type="button"
          onClick={refresh}
          disabled={busy}
          className="rounded border border-navy-950 bg-navy-950 px-3.5 py-2 text-sm font-medium text-warm-white transition-colors duration-[var(--duration-fast)] hover:bg-navy-800 disabled:cursor-not-allowed disabled:border-sage-300 disabled:bg-sage-200 disabled:text-navy-400"
        >
          {busy ? "Checking…" : "Re-check"}
        </button>
      </header>

      <div className="rounded border border-sage-300 bg-paper" aria-live="polite" aria-busy={busy}>
        <Row
          name="Web application"
          meta="GET /api/health"
          tone={probeTone(web)}
          detail={
            web.kind === "success" ? (
              <span>
                {web.data.service} v{web.data.version} · <Latency ms={web.latencyMs} />
              </span>
            ) : (
              <ErrorDetail probe={web} />
            )
          }
        />
        <Row
          name="API · liveness"
          meta="GET /healthz"
          tone={probeTone(liveness)}
          detail={
            liveness.kind === "success" ? (
              <span>
                {liveness.data.service} v{liveness.data.version} · {liveness.data.environment} ·{" "}
                <Latency ms={liveness.latencyMs} />
              </span>
            ) : (
              <ErrorDetail probe={liveness} />
            )
          }
        />
        <Row
          name="API · readiness"
          meta="GET /readyz"
          tone={probeTone(readiness, (d) => d.status === "ready")}
          label={
            readiness.kind === "success"
              ? readiness.data.status === "ready"
                ? "Ready"
                : "Not ready"
              : undefined
          }
          detail={
            readiness.kind === "success" ? (
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
                {checks.map(([name, check]) => (
                  <div key={name} className="contents">
                    <dt className="font-mono text-2xs leading-5 text-navy-400">{name}</dt>
                    <dd className="text-sm">
                      <span className={check.status === "ok" ? "text-forest-700" : "text-rust-700"}>
                        {check.status.replace("_", " ")}
                      </span>
                      {check.detail ? (
                        <span className="text-navy-400"> — {check.detail}</span>
                      ) : null}
                      {check.latency_ms !== null ? (
                        <>
                          {" "}
                          · <Latency ms={check.latency_ms} />
                        </>
                      ) : null}
                    </dd>
                  </div>
                ))}
              </dl>
            ) : (
              <ErrorDetail probe={readiness} />
            )
          }
        />
      </div>

      <footer className="mt-4 flex flex-wrap justify-between gap-2 font-mono text-2xs text-navy-400">
        <span>API base: {API_BASE_URL}</span>
        <span className="tabular">
          {checkedAt ? `Last checked ${checkedAt.toLocaleTimeString()}` : "Not checked yet"}
        </span>
      </footer>
    </section>
  );
}
