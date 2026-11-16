"use client";

import { useEffect, useState } from "react";

import { auth } from "@/lib/api/endpoints";
import type { SessionInfo } from "@/lib/api/types";

export type SignedInStatus = "loading" | "signed-in" | "visitor";

/*
 * The one place public pages (landing, status, sign-in, sign-up) learn whether a real
 * session exists. It asks the API and trusts only a clear yes:
 *   - "loading" until the answer arrives (callers must not treat it as signed in),
 *   - "visitor" for a 401, any other error, an unreachable API, or a reply that isn't a
 *     real signed-in session (a malformed body, or the API's no-login demo mode, where
 *     everybody is the demo user and nobody has signed in).
 * It only reads: no refresh, no redirect, nothing cleared. It is asked again on every page
 * load, and only calls made at the same moment share one request, so an old answer is never
 * reused after the session changed.
 */
let inFlight: Promise<SessionInfo | null> | null = null;
function probeSession(): Promise<SessionInfo | null> {
  inFlight ??= auth
    .peek()
    .then(
      (info) => (info?.auth_mode === "session" && typeof info.user?.id === "string" ? info : null),
      () => null,
    )
    .finally(() => {
      inFlight = null;
    });
  return inFlight;
}

export interface SessionProbe {
  status: SignedInStatus;
  /** The confirmed session, only when `status` is "signed-in". */
  info: SessionInfo | null;
}

export function useSessionProbe(): SessionProbe {
  const [probe, setProbe] = useState<SessionProbe>({ status: "loading", info: null });
  useEffect(() => {
    let active = true;
    void probeSession().then((info) => {
      if (active)
        setProbe(info ? { status: "signed-in", info } : { status: "visitor", info: null });
    });
    return () => {
      active = false;
    };
  }, []);
  return probe;
}

export function useSignedIn(): SignedInStatus {
  return useSessionProbe().status;
}
