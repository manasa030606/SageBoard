"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "@/lib/api/errors";
import {
  getLiveness,
  getReadiness,
  type HealthResponse,
  type ReadinessResponse,
} from "@/lib/api/health";

export type ProbeState<T> =
  | { kind: "loading" }
  | { kind: "success"; data: T; requestId: string | null; latencyMs: number }
  | { kind: "error"; error: ApiError };

export interface WebHealth {
  status: "ok";
  service: string;
  version: string;
  timestamp: string;
}

export interface SystemStatus {
  web: ProbeState<WebHealth>;
  liveness: ProbeState<HealthResponse>;
  readiness: ProbeState<ReadinessResponse>;
  checkedAt: Date | null;
  refresh: () => void;
}

async function timed<T>(
  fn: () => Promise<{ data: T; requestId: string | null }>,
): Promise<ProbeState<T>> {
  const start = performance.now();
  try {
    const { data, requestId } = await fn();
    return { kind: "success", data, requestId, latencyMs: Math.round(performance.now() - start) };
  } catch (error) {
    const apiError =
      error instanceof ApiError
        ? error
        : new ApiError({ status: 0, code: "UNKNOWN", message: String(error) });
    return { kind: "error", error: apiError };
  }
}

async function getWebHealth(signal: AbortSignal): Promise<{ data: WebHealth; requestId: null }> {
  const response = await fetch("/api/health", { cache: "no-store", signal });
  if (!response.ok) {
    throw new ApiError({
      status: response.status,
      code: "WEB_UNHEALTHY",
      message: "Web health check failed.",
    });
  }
  return { data: (await response.json()) as WebHealth, requestId: null };
}

export function useSystemStatus(): SystemStatus {
  const [web, setWeb] = useState<ProbeState<WebHealth>>({ kind: "loading" });
  const [liveness, setLiveness] = useState<ProbeState<HealthResponse>>({ kind: "loading" });
  const [readiness, setReadiness] = useState<ProbeState<ReadinessResponse>>({ kind: "loading" });
  const [checkedAt, setCheckedAt] = useState<Date | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  const run = useCallback(async () => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    const { signal } = controller;

    setWeb({ kind: "loading" });
    setLiveness({ kind: "loading" });
    setReadiness({ kind: "loading" });

    const [w, l, r] = await Promise.all([
      timed(() => getWebHealth(signal)),
      timed(() => getLiveness({ signal })),
      timed(() => getReadiness({ signal })),
    ]);
    if (signal.aborted) return;
    setWeb(w);
    setLiveness(l);
    setReadiness(r);
    setCheckedAt(new Date());
  }, []);

  useEffect(() => {
    // Runs once on mount; state updates happen after the awaited requests resolve.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void run();
    return () => controllerRef.current?.abort();
  }, [run]);

  return { web, liveness, readiness, checkedAt, refresh: () => void run() };
}
