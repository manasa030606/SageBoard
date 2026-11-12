import { connection } from "next/server";

import { WEB_VERSION } from "@/lib/version";

/**
 * Frontend liveness endpoint: GET /api/health.
 * `connection()` opts out of build-time prerendering so the timestamp is per request.
 */
export async function GET() {
  await connection();
  return Response.json(
    {
      status: "ok",
      service: "sageboard-web",
      version: WEB_VERSION,
      timestamp: new Date().toISOString(),
    },
    { headers: { "Cache-Control": "no-store" } },
  );
}
