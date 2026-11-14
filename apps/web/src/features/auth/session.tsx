"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { onUnauthenticated } from "@/lib/api/client";
import { auth } from "@/lib/api/endpoints";
import { ApiError } from "@/lib/api/errors";
import type { SessionInfo, User } from "@/lib/api/types";

type Status = "loading" | "authenticated" | "unauthenticated" | "unavailable";

interface SessionContextValue {
  status: Status;
  user: User | null;
  authMode: SessionInfo["auth_mode"] | null;
  error: ApiError | null;
  signOut: () => Promise<void>;
  retry: () => void;
}

const SessionContext = createContext<SessionContextValue | null>(null);

/**
 * Full page load (not a client-side transition) whenever the session changes.
 * Next.js keeps visited pages' state alive in the background; a reload guarantees
 * nothing from the previous session — data or "signed out" state — survives.
 */
export function hardNavigate(href: string): void {
  window.location.assign(href);
}

export function loginHref(next: string | null): string {
  return next && next.startsWith("/app") ? `/login?next=${encodeURIComponent(next)}` : "/login";
}

/**
 * Loads the signed-in user for the app area and redirects to /login when there is no
 * session. The API is the authority: this only decides what to render.
 */
export function SessionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<{
    status: Status;
    info: SessionInfo | null;
    error: ApiError | null;
  }>({
    status: "loading",
    info: null,
    error: null,
  });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    auth
      .me()
      .then((info) => active && setState({ status: "authenticated", info, error: null }))
      .catch((error: unknown) => {
        if (!active) return;
        const apiError = error instanceof ApiError ? error : null;
        if (apiError && apiError.status === 401) {
          setState({ status: "unauthenticated", info: null, error: null });
        } else {
          setState({ status: "unavailable", info: null, error: apiError });
        }
      });
    return () => {
      active = false;
    };
  }, [attempt]);

  useEffect(
    () => onUnauthenticated(() => setState({ status: "unauthenticated", info: null, error: null })),
    [],
  );

  useEffect(() => {
    // Read the URL here (client-only, after render) rather than with usePathname, so
    // the provider doesn't make the whole app area wait on request data.
    if (state.status === "unauthenticated") hardNavigate(loginHref(window.location.pathname));
  }, [state.status]);

  const signOut = useCallback(async () => {
    try {
      await auth.logout();
    } finally {
      hardNavigate("/login");
    }
  }, []);

  const value = useMemo<SessionContextValue>(
    () => ({
      status: state.status,
      user: state.info?.user ?? null,
      authMode: state.info?.auth_mode ?? null,
      error: state.error,
      signOut,
      retry: () => setAttempt((a) => a + 1),
    }),
    [state, signOut],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession must be used inside <SessionProvider>");
  return value;
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const letters =
    parts.length > 1 ? parts[0]![0]! + parts.at(-1)![0]! : (parts[0] ?? "?").slice(0, 2);
  return letters.toUpperCase();
}
