import { afterEach, describe, expect, it, vi } from "vitest";

import { apiRequest, onUnauthenticated, setCsrfToken } from "./client";

const BASE = "http://api.test/api/v1";

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const expired = () =>
  json(401, {
    error: { code: "TOKEN_EXPIRED", message: "Your session has expired.", details: {} },
  });

afterEach(() => setCsrfToken(null));

describe("CSRF header", () => {
  it("is sent on state-changing requests only", async () => {
    setCsrfToken("tok-123");
    const fetchImpl = vi.fn<typeof fetch>(async () => json(200, { ok: true }));
    await apiRequest("/things", { baseUrl: BASE, fetchImpl });
    await apiRequest("/things", { method: "POST", body: {}, baseUrl: BASE, fetchImpl });
    await apiRequest("/things/1", { method: "DELETE", baseUrl: BASE, fetchImpl });
    const headers = fetchImpl.mock.calls.map(([, init]) => init?.headers as Record<string, string>);
    expect(headers[0]!["X-CSRF-Token"]).toBeUndefined();
    expect(headers[1]!["X-CSRF-Token"]).toBe("tok-123");
    expect(headers[2]!["X-CSRF-Token"]).toBe("tok-123");
  });
});

describe("session refresh", () => {
  it("refreshes once on 401, retries, and adopts the new CSRF token", async () => {
    const fetchImpl = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(expired())
      .mockResolvedValueOnce(json(200, { csrf_token: "fresh", user: {}, auth_mode: "session" }))
      .mockResolvedValueOnce(json(200, { items: [] }));

    const res = await apiRequest<{ items: unknown[] }>("/datasets", { baseUrl: BASE, fetchImpl });

    expect(res.data).toEqual({ items: [] });
    const urls = fetchImpl.mock.calls.map(([url]) => String(url));
    expect(urls).toEqual([`${BASE}/datasets`, `${BASE}/auth/refresh`, `${BASE}/datasets`]);
    const next = vi.fn<typeof fetch>(async () => json(200, {}));
    await apiRequest("/x", { method: "POST", baseUrl: BASE, fetchImpl: next });
    const sent = next.mock.calls[0]![1]!.headers as Record<string, string>;
    expect(sent["X-CSRF-Token"]).toBe("fresh");
  });

  it("shares one refresh between concurrent requests", async () => {
    let refreshCalls = 0;
    const seen = new Map<string, number>();
    const fetchImpl = vi.fn<typeof fetch>(async (url): Promise<Response> => {
      const u = String(url);
      if (u.endsWith("/auth/refresh")) {
        refreshCalls += 1;
        await new Promise((r) => setTimeout(r, 5));
        return json(200, { csrf_token: "t", user: {}, auth_mode: "session" });
      }
      const count = (seen.get(u) ?? 0) + 1;
      seen.set(u, count);
      return count === 1 ? expired() : json(200, { u });
    });
    await Promise.all([
      apiRequest("/a", { baseUrl: BASE, fetchImpl }),
      apiRequest("/b", { baseUrl: BASE, fetchImpl }),
    ]);
    expect(refreshCalls).toBe(1);
  });

  it("notifies listeners when the refresh also fails", async () => {
    const listener = vi.fn();
    const stop = onUnauthenticated(listener);
    const fetchImpl = vi.fn<typeof fetch>(async () => expired());
    await expect(apiRequest("/datasets", { baseUrl: BASE, fetchImpl })).rejects.toMatchObject({
      status: 401,
      code: "TOKEN_EXPIRED",
    });
    expect(listener).toHaveBeenCalledTimes(1);
    expect(fetchImpl).toHaveBeenCalledTimes(2); // original + one refresh attempt, no loop
    stop();
  });

  it("never tries to refresh for auth endpoints themselves", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async () =>
      json(401, { error: { code: "INVALID_CREDENTIALS", message: "No match.", details: {} } }),
    );
    await expect(
      apiRequest("/auth/login", { method: "POST", body: {}, baseUrl: BASE, fetchImpl }),
    ).rejects.toMatchObject({ code: "INVALID_CREDENTIALS" });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });
});

describe("bodies and responses", () => {
  it("sends FormData as multipart (no JSON content type)", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async () => json(201, { ok: true }));
    const form = new FormData();
    form.append("file", new Blob(["a,b\n1,2\n"]), "x.csv");
    await apiRequest("/datasets/uploads", { method: "POST", body: form, baseUrl: BASE, fetchImpl });
    const init = fetchImpl.mock.calls[0]![1]!;
    expect(init.body).toBe(form);
    expect((init.headers as Record<string, string>)["Content-Type"]).toBeUndefined();
  });

  it("builds query strings and skips empty values", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async () => json(200, {}));
    await apiRequest("/history/queries", {
      query: { limit: 25, cursor: null, origin: "", dataset_id: undefined, reveal: false },
      baseUrl: BASE,
      fetchImpl,
    });
    expect(String(fetchImpl.mock.calls[0]![0])).toBe(
      `${BASE}/history/queries?limit=25&reveal=false`,
    );
  });

  it("returns undefined for 204 and text for text responses", async () => {
    const noContent = vi.fn<typeof fetch>(async () => new Response(null, { status: 204 }));
    expect(
      (await apiRequest("/x", { method: "DELETE", baseUrl: BASE, fetchImpl: noContent })).data,
    ).toBeUndefined();
    const text = vi.fn<typeof fetch>(async () => new Response("# Title\n", { status: 200 }));
    const res = await apiRequest<string>("/r.md", {
      responseType: "text",
      baseUrl: BASE,
      fetchImpl: text,
    });
    expect(res.data).toBe("# Title\n");
  });
});
