/**
 * Response headers for every page (applied in next.config.ts).
 *
 * The CSP covers what does not need a per-request nonce: who may frame the app, what `<base>`
 * and form targets may be, and no plugins. A script-src policy needs nonces with this Next.js
 * setup and is not added yet (see docs/security/SECURITY.md).
 */
const csp = [
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
];

export function securityHeaders(production: boolean): { key: string; value: string }[] {
  const headers = [
    { key: "X-Content-Type-Options", value: "nosniff" },
    { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
    { key: "X-Frame-Options", value: "DENY" },
    { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
    { key: "Content-Security-Policy", value: csp.join("; ") },
  ];
  // Browsers ignore HSTS over plain HTTP, but keep it out of development to avoid pinning localhost.
  if (production) {
    headers.push({
      key: "Strict-Transport-Security",
      value: "max-age=31536000; includeSubDomains",
    });
  }
  return headers;
}
