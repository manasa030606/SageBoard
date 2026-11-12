/** Mirrors the backend error envelope (API_SPECIFICATION §1.3). */
export interface ErrorEnvelope {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
    request_id?: string | null;
  };
}

/** Client-side codes for failures that never reached (or never left) the server. */
export type ClientErrorCode = "NETWORK_ERROR" | "TIMEOUT" | "ABORTED" | "INVALID_RESPONSE";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string | null;
  readonly details: Record<string, unknown>;

  constructor(opts: {
    status: number;
    code: string;
    message: string;
    requestId?: string | null;
    details?: Record<string, unknown>;
  }) {
    super(opts.message);
    this.name = "ApiError";
    this.status = opts.status;
    this.code = opts.code;
    this.requestId = opts.requestId ?? null;
    this.details = opts.details ?? {};
  }

  /** True when the request never got an HTTP response (offline, DNS, CORS, timeout). */
  get isClientSide(): boolean {
    return this.status === 0;
  }
}

export function isErrorEnvelope(value: unknown): value is ErrorEnvelope {
  if (typeof value !== "object" || value === null || !("error" in value)) return false;
  const error = (value as { error: unknown }).error;
  return (
    typeof error === "object" &&
    error !== null &&
    typeof (error as { code?: unknown }).code === "string" &&
    typeof (error as { message?: unknown }).message === "string"
  );
}
