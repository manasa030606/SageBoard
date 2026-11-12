import { describe, expect, it, vi } from "vitest";

import { apiRequest } from "./client";
import { ApiError } from "./errors";
import { getReadiness } from "./health";

const BASE = "http://api.test/api/v1";

function jsonResponse(status: number, body: unknown, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

describe("apiRequest", () => {
  it("returns parsed data, status and request id on success", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async () =>
      jsonResponse(200, { status: "ok" }, { "X-Request-ID": "req_1" }),
    );

    const res = await apiRequest<{ status: string }>("/healthz", { baseUrl: BASE, fetchImpl });

    expect(res).toEqual({ status: 200, data: { status: "ok" }, requestId: "req_1" });
    const [url, init] = fetchImpl.mock.calls[0]!;
    expect(url).toBe(`${BASE}/healthz`);
    expect(init?.credentials).toBe("include");
    expect(init?.method).toBe("GET");
  });

  it("serialises JSON bodies with a content type", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async () => jsonResponse(201, { id: "x" }));
    await apiRequest("/things", { method: "POST", body: { a: 1 }, baseUrl: BASE, fetchImpl });
    const init = fetchImpl.mock.calls[0]![1]!;
    expect(init.body).toBe('{"a":1}');
    expect((init.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
  });

  it("maps the backend error envelope to ApiError", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async () =>
      jsonResponse(404, {
        error: { code: "NOT_FOUND", message: "Nope", details: { id: 1 }, request_id: "req_9" },
      }),
    );

    const err = await apiRequest("/x", { baseUrl: BASE, fetchImpl }).catch((e: unknown) => e);

    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({
      status: 404,
      code: "NOT_FOUND",
      message: "Nope",
      requestId: "req_9",
      details: { id: 1 },
    });
  });

  it("reports network failures (incl. CORS rejections) as NETWORK_ERROR", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async () => {
      throw new TypeError("Failed to fetch");
    });
    const err = (await apiRequest("/x", { baseUrl: BASE, fetchImpl }).catch(
      (e: unknown) => e,
    )) as ApiError;
    expect(err.code).toBe("NETWORK_ERROR");
    expect(err.isClientSide).toBe(true);
  });

  it("reports timeouts as TIMEOUT", async () => {
    const fetchImpl = vi.fn<typeof fetch>(
      (_url, init) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () =>
            reject(new DOMException("aborted", "AbortError")),
          );
        }),
    );
    const err = (await apiRequest("/slow", { baseUrl: BASE, fetchImpl, timeoutMs: 20 }).catch(
      (e: unknown) => e,
    )) as ApiError;
    expect(err.code).toBe("TIMEOUT");
  });

  it("treats a non-envelope error body as INVALID_RESPONSE", async () => {
    const fetchImpl = vi.fn<typeof fetch>(
      async () => new Response("<html>bad gateway</html>", { status: 502 }),
    );
    const err = (await apiRequest("/x", { baseUrl: BASE, fetchImpl }).catch(
      (e: unknown) => e,
    )) as ApiError;
    expect(err).toMatchObject({ status: 502, code: "INVALID_RESPONSE" });
  });
});

describe("getReadiness", () => {
  it("returns the readiness report even when the API answers 503", async () => {
    const report = { status: "not_ready", checks: { database: { status: "unavailable" } } };
    const fetchImpl = vi.fn<typeof fetch>(async () => jsonResponse(503, report));

    const res = await getReadiness({ baseUrl: BASE, fetchImpl });

    expect(res.status).toBe(503);
    expect(res.data.status).toBe("not_ready");
  });
});
