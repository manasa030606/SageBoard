import { afterEach, describe, expect, it, vi } from "vitest";

import { conversations, reports } from "./endpoints";

function stubFetch(status: number, body: unknown) {
  const impl = vi.fn<typeof fetch>(async (_url, init) => {
    // Mirror the browser: a GET or HEAD request with a body is rejected before it is sent.
    if (init?.body !== undefined && ["GET", "HEAD"].includes(init.method ?? "GET")) {
      throw new TypeError("Request with GET/HEAD method cannot have body.");
    }
    return new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", impl);
  return impl;
}

afterEach(() => vi.unstubAllGlobals());

describe("create endpoints use POST", () => {
  it("reports.create posts the session id to /reports", async () => {
    const fetchImpl = stubFetch(201, { id: "r1", title: "T" });
    const created = await reports.create("s1");
    const [url, init] = fetchImpl.mock.calls[0]!;
    expect(String(url)).toMatch(/\/reports$/);
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({ analysis_session_id: "s1" });
    expect(created.id).toBe("r1");
  });

  it("reports.create passes an explicit title", async () => {
    const fetchImpl = stubFetch(201, { id: "r1", title: "Mine" });
    await reports.create("s1", "Mine");
    expect(JSON.parse(String(fetchImpl.mock.calls[0]![1]!.body))).toEqual({
      analysis_session_id: "s1",
      title: "Mine",
    });
  });

  it("conversations.create and conversations.ask post too", async () => {
    const fetchImpl = stubFetch(201, { id: "c1" });
    await conversations.create("d1");
    await conversations.ask("c1", "How many orders?");
    expect(fetchImpl.mock.calls.map(([, init]) => init?.method)).toEqual(["POST", "POST"]);
    expect(String(fetchImpl.mock.calls[1]![0])).toMatch(/\/conversations\/c1\/sessions$/);
  });
});
