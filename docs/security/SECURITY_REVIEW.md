# Security review (Phase 10)

Scope: the whole application as of Phase 10, reviewed from the code and by running attacks against a real API and Postgres. Nothing was deployed. Evidence for each finding is in the tests named below; behaviour is described in [SECURITY.md](SECURITY.md).

**Not tested:** how a live model behaves under prompt injection. The evaluation's oracle mode replaces the model, so it can only show that the *structure* holds (the boundary, the Guard and the database roles). See "Remaining risks".

## Summary

| Severity | Found | Fixed | Remaining |
|---|---|---|---|
| Critical | 0 | – | 0 |
| High | 1 | 1 | 0 |
| Medium | 4 | 4 | 0 |
| Low | 4 | 4 | 0 |
| Accepted / documented | 9 | – | 9 |

## Findings and fixes

| ID | Severity | Finding | Fix | Regression test |
|---|---|---|---|---|
| H1 | High | A database error message included the bound parameters. Reproduced: a duplicate-signup error contained the email and the password hash, and error text reaches logs. | `hide_parameters=True` on the engine (`app/db/session.py`). | `test_hardening_pg.py` (DB errors contain no bound values) |
| M1 | Medium | A valid 20 MB CSV (388k rows, about 2.7 s of CPU in a worker thread) stalled the event loop: `/healthz` max 2,267 ms, p95 140 ms during the load. | Shorter GIL switch interval at startup (`GIL_SWITCH_INTERVAL_S = 0.0002`, `app/main.py`). Max fell to 149 ms, p95 to 20 ms; upload time unchanged. | Measured with `scripts/perf_probe.py` (see PERFORMANCE_REPORT.md); no unit test, because it is a timing property |
| M2 | Medium | No limit on how many analyses one user could run at once, so one user could fill the shared run slots. | `ANALYSES_CONCURRENT_PER_USER` (default 2); the third request gets `429` with `Retry-After`. | `test_hardening_pg.py` (cap of 2), `test_hardening.py` (`active_for` per owner) |
| M3 | Medium | No security headers on API responses; no JSON body-size cap; the web app had no CSP or HSTS. | `SecurityHeadersMiddleware` and `BodyLimitMiddleware` (`app/core/middleware.py`); `securityHeaders()` in `next.config.ts`. Checked with curl on a production web build. | `test_hardening.py` (headers, HSTS, declared and chunked 413, upload path), `security-headers.test.ts` |
| M4 | Medium | The prompt data boundary only escaped one exact spelling of the closing tag. | `data_block()` neutralises `<data` and `</data` in any case or spacing. | `test_hardening.py` (7 variants) |
| L1 | Low | The read-only executor fetched every row and truncated afterwards. | Fetches `max_rows + 1` through a cursor. | `test_hardening_pg.py` (bounded fetch; fails without the fix) |
| L2 | Low | Two simultaneous signups with one email: the loser got a 500. | `IntegrityError` becomes `409 EMAIL_TAKEN`. | `test_hardening_pg.py` |
| L3 | Low | `/docs` and `/openapi.json` were public in production. | Disabled when `ENV=production`. | `test_hardening.py` |
| L4 | Low | Raw exception text in some agent and provider log lines. | Log only `error_type` or `code`. | Covered by the redaction tests; reviewed by reading the log call sites |

Every new test was checked against the unfixed code and fails there.

## What was checked and found sound

| Area | Result |
|---|---|
| Ownership (IDOR) | `tests/integration/test_ownership.py` drives all 38 operations in the OpenAPI document with a second user: every foreign id gives 404, lists return nothing. It fails if a route cannot be checked, so new routes are covered. Agent runs, reports, history and the PDF export are included. |
| Authentication | Algorithm pinned, required claims checked, refresh rotation with reuse detection, argon2id, generic login errors with a dummy hash check. Login rate limit returns 429 after 5 attempts. |
| CSRF, CORS, cookies | Missing or wrong token gives 403. A foreign origin gets no CORS headers; the allowed origin does. `HttpOnly`, `SameSite=Lax`, and the refresh cookie only on `/api/v1/auth`. |
| Database isolation | The SQL Guard and the read-only role are independent layers: the safety suite runs the Guard-bypassed corpus against the database roles. Result files are unchanged from the committed ones except a timing figure. |
| SQL injection | Existing adversarial corpus (150+ cases) rejected by the Guard; with the Guard bypassed, blocked or harmless at the database. The agent's only path to execution is `guard_validate` then `run_readonly` (checked by reading `app/agent/nodes/sql.py` and `tools/executor.py`). Oracle evaluation cases X04 to X08 (`pg_sleep`, `CREATE TABLE`, `UPDATE`, the users table, `/etc/passwd`) are refused. |
| CSV upload | `.exe` gives 415; NUL bytes, 300 columns and a traversal filename are rejected. 30, 100 and 400 MB uploads are refused quickly; server memory stayed flat at 35 MB. |
| Error output | 404, 405 and 422 envelopes leak nothing. Database connection failures give a generic 503. |
| Logging | Keys matching password, secret, token, key, authorization or cookie are redacted. After H1 and L4, no bound values or exception text reach logs. The `agent.run_finished` log line carries only counts and codes. |
| Agent limits | Steps and retries are bounded; validation cannot be skipped (the executor takes only validated SQL); run state is per run, with no per-user state shared between runs. |
| Dependencies | `pip-audit` and `pnpm audit --prod`: no known vulnerabilities (November 2026). |
| Pools | App 5+5, ingest 3, executor 5; at most 4 runs at a time. |

## Remaining risks (accepted and documented)

| Item | Why it is accepted |
|---|---|
| Live-model prompt-injection resistance is untested | Needs a live key and quota. Containment does not depend on the model: the worst a manipulated model can produce is a SELECT on the user's own data, after the Guard and a read-only role. |
| Logout leaves the access token valid for up to 15 minutes | Short lifetime; the refresh family is revoked at once. |
| Registration reveals whether an email exists | Needed for a clear sign-up error; login does not leak it. |
| Rate limits, run slots and the per-user cap are in process | Single-instance design (ADR-0004). Behind a proxy the limits need `--proxy-headers`. |
| Default `ENV` is `development` | Production refusals only apply when `ENV=production`. A forgotten setting is insecure, so it is the first item of the deployment checklist. |
| No `script-src` in the CSP | Next.js inline scripts need per-request nonces; a partial CSP is shipped instead. |
| Stored results show real emails to their owner | Masking applies to model-bound payloads, not to the owner's own screen. |
| A sensitive column aliased in a query can reach the model | Redaction works on result column names. |
| A wrong answer that executes cleanly (evaluation R06) | Cannot be detected without knowing the truth. |

## Verdict

No Critical or High issue remains. The review changes the deployment risk from "forgotten settings and abuse by one user" to the items above, which are limits of the single-instance design rather than defects.
