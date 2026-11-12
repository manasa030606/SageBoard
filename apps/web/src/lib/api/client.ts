import { API_BASE_URL } from "@/lib/env";

import { ApiError, isErrorEnvelope } from "./errors";

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
  /** Abort the request after this many milliseconds (default 10 s). */
  timeoutMs?: number;
  /**
   * Non-2xx statuses whose body is a normal payload rather than an error envelope
   * (e.g. /readyz returns its report with 503).
   */
  acceptStatuses?: readonly number[];
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

/**
 * Typed fetch wrapper for the Sageboard API.
 *
 * - Sends cookies (`credentials: "include"`) so session auth works from Phase 2.
 * - Converts every failure into an `ApiError`, including network/CORS failures and
 *   timeouts, so UI code handles exactly one error type.
 */
export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {},
): Promise<ApiResponse<T>> {
  const {
    method = "GET",
    body,
    signal,
    timeoutMs = DEFAULT_TIMEOUT_MS,
    acceptStatuses = [],
    baseUrl = API_BASE_URL,
    fetchImpl = fetch,
  } = options;

  const timeout = AbortSignal.timeout(timeoutMs);
  const combined = signal ? AbortSignal.any([signal, timeout]) : timeout;
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";

  let response: Response;
  try {
    response = await fetchImpl(`${baseUrl}${path.startsWith("/") ? path : `/${path}`}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
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

  const requestId = response.headers.get("X-Request-ID");
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
