/**
 * Public (browser-visible) configuration.
 *
 * Only NEXT_PUBLIC_* variables reach the browser, and Next.js inlines them at build
 * time — so they must never contain secrets. Server-only secrets do not exist in the
 * web app at all: every privileged call goes through the FastAPI backend.
 */

const DEFAULT_API_URL = "http://localhost:8000/api/v1";

export function normalizeApiUrl(raw: string | undefined): string {
  const value = (raw ?? "").trim() || DEFAULT_API_URL;
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new Error(`NEXT_PUBLIC_API_URL is not a valid URL: "${value}"`);
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new Error(`NEXT_PUBLIC_API_URL must use http or https: "${value}"`);
  }
  return url.toString().replace(/\/+$/, "");
}

// Must be referenced literally (not via a variable key) so Next.js can inline it.
export const API_BASE_URL = normalizeApiUrl(process.env.NEXT_PUBLIC_API_URL);
