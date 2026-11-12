import { apiRequest, type ApiResponse, type RequestOptions } from "./client";

/*
 * Hand-written to mirror apps/api/app/schemas/health.py for Phase 1.
 * From Phase 8 these types are generated from the backend's OpenAPI schema.
 */
export type CheckStatus = "ok" | "unavailable" | "not_configured";

export interface HealthResponse {
  status: "ok";
  service: string;
  version: string;
  environment: string;
  timestamp: string;
}

export interface DependencyCheck {
  status: CheckStatus;
  latency_ms: number | null;
  detail: string | null;
}

export interface ReadinessResponse {
  status: "ready" | "not_ready";
  service: string;
  version: string;
  timestamp: string;
  checks: Record<string, DependencyCheck>;
}

type Opts = Pick<RequestOptions, "signal" | "timeoutMs" | "baseUrl" | "fetchImpl">;

export function getLiveness(opts: Opts = {}): Promise<ApiResponse<HealthResponse>> {
  return apiRequest<HealthResponse>("/healthz", opts);
}

/** Readiness answers 503 with a full report when a dependency is down. */
export function getReadiness(opts: Opts = {}): Promise<ApiResponse<ReadinessResponse>> {
  return apiRequest<ReadinessResponse>("/readyz", { ...opts, acceptStatuses: [503] });
}
