import { API_BASE_URL } from "@/lib/env";

import { ApiError, isErrorEnvelope } from "./errors";

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  /** JSON-serialisable value, or FormData for file uploads (sent as multipart). */
  body?: unknown;
  query?: Record<string, string | number | boolean | null | undefined>;
  signal?: AbortSignal;
  /** Abort the request after this many milliseconds (default 10 s). */
  timeoutMs?: number;
  /**
   * Non-2xx statuses whose body is a normal payload rather than an error envelope
   * (e.g. /readyz returns its report with 503).
   */
  acceptStatuses?: readonly number[];
  /** Expect a text body (e.g. a Markdown download) instead of JSON. */
  responseType?: "json" | "text" | "blob";
  /** Try one silent token refresh on 401 before failing (default true). */
  retryOnAuth?: boolean;
  /** Override for tests; defaults to the configured API base URL. */
  baseUrl?: string;
  fetchImpl?: typeof fetch;
}

export interface ApiResponse<T> {
  status: number;
  data: T;
  requestId: string | null;
}

const DEFAULT_TIMEOUT_MS = 10_000;
const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);

/*
 * CSRF double-submit token. The API sets it as a cookie and also returns it in the
 * body of every session response; we keep it in memory and echo it in a header on
 * state-changing requests. (Reading it from the body, not document.cookie, also
 * works when the web app and the API are on different sites.)
 */
let csrfToken: string | null = null;
export function setCsrfToken(token: string | null): void {
  csrfToken = token || null;
}

type Listener = () => void;
const unauthenticatedListeners = new Set<Listener>();
/** Called when a request fails with 401 even after a refresh attempt (session over). */
export function onUnauthenticated(listener: Listener): () => void {
  unauthenticatedListeners.add(listener);
  return () => unauthenticatedListeners.delete(listener);
}

let refreshing: Promise<boolean> | null = null;
/** One refresh at a time, shared by every request that hit a 401 meanwhile. */
function refreshSession(baseUrl: string, fetchImpl: typeof fetch): Promise<boolean> {
  refreshing ??= (async () => {
    try {
      const res = await apiRequest<{ csrf_token: string }>("/auth/refresh", {
        method: "POST",
        baseUrl,
        fetchImpl,
        retryOnAuth: false,
      });
      setCsrfToken(res.data.csrf_token);
      return true;
    } catch {
      return false;
    } finally {
      refreshing = null;
    }
  })();
  return refreshing;
}

function buildUrl(baseUrl: string, path: string, query?: RequestOptions["query"]): string {
  const url = `${baseUrl}${path.startsWith("/") ? path : `/${path}`}`;
  if (!query) return url;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  }
  const qs = params.toString();
  return qs ? `${url}?${qs}` : url;
}

/**
 * Typed fetch wrapper for the Sageboard API.
 *
 * - Sends cookies (`credentials: "include"`) so session auth works.
 * - Adds the CSRF header on POST/PUT/PATCH/DELETE.
 * - On 401, refreshes the session once and retries; if that fails, notifies listeners.
 * - Converts every failure into an `ApiError`, including network/CORS failures and
 *   timeouts, so UI code handles exactly one error type.
 */
export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {},
): Promise<ApiResponse<T>> {
  const {
    body,
    method = body === undefined ? "GET" : "POST",
    query,
    signal,
    timeoutMs = DEFAULT_TIMEOUT_MS,
    acceptStatuses = [],
    responseType = "json",
    retryOnAuth = true,
    baseUrl = API_BASE_URL,
    fetchImpl = fetch,
  } = options;

  const timeout = AbortSignal.timeout(timeoutMs);
  const combined = signal ? AbortSignal.any([signal, timeout]) : timeout;
  const headers: Record<string, string> = {
    Accept:
      responseType === "text"
        ? "text/markdown, text/plain, application/json"
        : responseType === "blob"
          ? "application/pdf, application/json"
          : "application/json",
  };
  const isForm = typeof FormData !== "undefined" && body instanceof FormData;
  if (body !== undefined && !isForm) headers["Content-Type"] = "application/json";
  if (UNSAFE.has(method) && csrfToken) headers["X-CSRF-Token"] = csrfToken;

  let response: Response;
  try {
    response = await fetchImpl(buildUrl(baseUrl, path, query), {
      method,
      headers,
      body: body === undefined ? undefined : isForm ? (body as FormData) : JSON.stringify(body),
      credentials: "include",
      signal: combined,
      cache: "no-store",
    });
  } catch (cause) {
    if (timeout.aborted) {
      throw new ApiError({
        status: 0,
        code: "TIMEOUT",
        message: "The server took too long to respond.",
      });
    }
    if (signal?.aborted) {
      throw new ApiError({ status: 0, code: "ABORTED", message: "The request was cancelled." });
    }
    throw new ApiError({
      status: 0,
      code: "NETWORK_ERROR",
      message: "Could not reach the Sageboard API. Check that the backend is running.",
      details: { cause: cause instanceof Error ? cause.message : String(cause) },
    });
  }

  if (response.status === 401 && retryOnAuth && !path.startsWith("/auth/")) {
    if (await refreshSession(baseUrl, fetchImpl)) {
      return apiRequest<T>(path, { ...options, retryOnAuth: false });
    }
    unauthenticatedListeners.forEach((listener) => listener());
  }

  const requestId = response.headers.get("X-Request-ID");

  if (response.status === 204) {
    return { status: 204, data: undefined as T, requestId };
  }
  if (response.ok && responseType === "text") {
    return { status: response.status, data: (await response.text()) as T, requestId };
  }

  if (response.ok && responseType === "blob") {
    return { status: response.status, data: (await response.blob()) as T, requestId };
  }

  const payload: unknown = await readJson(response);

  if (response.ok || acceptStatuses.includes(response.status)) {
    if (payload === undefined) {
      throw new ApiError({
        status: response.status,
        code: "INVALID_RESPONSE",
        message: "The server returned an unexpected response.",
        requestId,
      });
    }
    return { status: response.status, data: payload as T, requestId };
  }

  if (isErrorEnvelope(payload)) {
    throw new ApiError({
      status: response.status,
      code: payload.error.code,
      message: payload.error.message,
      requestId: payload.error.request_id ?? requestId,
      details: payload.error.details,
    });
  }
  throw new ApiError({
    status: response.status,
    code: "INVALID_RESPONSE",
    message: `Unexpected response from the server (HTTP ${response.status}).`,
    requestId,
  });
}

async function readJson(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return undefined;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return undefined;
  }
}
