"use client";

import { useEffect, useRef, useState } from "react";

import { analysis } from "@/lib/api/endpoints";
import type { NodeRun, SessionDetail } from "@/lib/api/types";
import type { ApiError } from "@/lib/api/errors";
import { toApiError } from "@/lib/use-api";

const ACTIVE = new Set(["queued", "running"]);
const POLL_MS = 1500;
const RETRY_MS = 4000;

/**
 * Loads a session and keeps polling (detail + trace) while it is queued/running.
 * Terminal sessions resolve in one fetch and stop. `onSettled` fires once when the
 * session leaves the active states.
 */
export function useLiveSession(
  sessionId: string | null,
  onSettled?: (detail: SessionDetail) => void,
): { detail: SessionDetail | undefined; trace: NodeRun[]; error: ApiError | undefined } {
  const [detail, setDetail] = useState<SessionDetail>();
  const [trace, setTrace] = useState<NodeRun[]>([]);
  const [error, setError] = useState<ApiError>();
  const settledRef = useRef(onSettled);
  useEffect(() => {
    settledRef.current = onSettled;
  });

  useEffect(() => {
    if (!sessionId) return;
    let active = true;
    let timer: number | undefined;
    let settled = false;

    async function tick(): Promise<void> {
      if (!sessionId) return;
      try {
        const next = await analysis.get(sessionId);
        if (!active) return;
        setDetail(next);
        setError(undefined);
        try {
          const nodes = await analysis.trace(sessionId);
          if (active) setTrace(nodes);
        } catch {
          // trace is progress decoration; the session detail is the source of truth
        }
        if (ACTIVE.has(next.status)) {
          timer = window.setTimeout(() => void tick(), POLL_MS);
        } else if (!settled) {
          settled = true;
          settledRef.current?.(next);
        }
      } catch (err) {
        if (!active) return;
        setError(toApiError(err));
        timer = window.setTimeout(() => void tick(), RETRY_MS);
      }
    }

    void tick();
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [sessionId]);

  return { detail, trace, error };
}
