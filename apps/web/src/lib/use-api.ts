"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "@/lib/api/errors";

export interface ApiState<T> {
  data: T | undefined;
  error: ApiError | undefined;
  /** True while the current request is in flight (old data stays visible). */
  loading: boolean;
  /** Re-run the request. */
  reload: () => void;
  /** Replace the data locally after a successful mutation. */
  setData: (data: T) => void;
}

export function toApiError(error: unknown): ApiError {
  return error instanceof ApiError
    ? error
    : new ApiError({ status: 0, code: "UNKNOWN", message: "Something went wrong." });
}

type Dep = string | number | boolean | null | undefined;

/**
 * Load data from the API on mount and whenever `deps` change; stale responses are
 * ignored. `deps` are plain values (ids, filters) so they can form a request key:
 * the hook is "loading" until a response for the current key arrives.
 */
export function useApi<T>(load: () => Promise<T>, deps: readonly Dep[]): ApiState<T> {
  const [tick, setTick] = useState(0);
  const key = JSON.stringify([...deps, tick]);
  const [state, setState] = useState<{ key?: string; data?: T; error?: ApiError }>({});
  const loadRef = useRef(load);

  useEffect(() => {
    loadRef.current = load;
  });

  useEffect(() => {
    let active = true;
    loadRef
      .current()
      .then((data) => active && setState({ key, data }))
      .catch(
        (e: unknown) => active && setState((s) => ({ key, data: s.data, error: toApiError(e) })),
      );
    return () => {
      active = false;
    };
  }, [key]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  const setData = useCallback((data: T) => setState((s) => ({ ...s, data, error: undefined })), []);
  const current = state.key === key;
  return {
    data: state.data,
    error: current ? state.error : undefined,
    loading: !current,
    reload,
    setData,
  };
}

export function errorMessage(error: unknown): string {
  return toApiError(error).message;
}
