# Sageboard — Security Design

| Field | Value |
|---|---|
| Document | SECURITY_DESIGN v0.2 |
| Status | Approved 2026-11-12 (v0.2). Decisions: see DECISION_LOG.md |
| Principle | Defense in depth: no single layer (especially not the prompt) is relied on for safety |

---

## 1. Assets and trust boundaries

**Assets:** user datasets, user credentials/sessions, LLM API key and DB credentials, other users' data, service availability, LLM budget.

```
 [Browser]──TB1──▶[FastAPI]──TB2──▶[LLM provider]
                     │
                    TB3 (app role, rw)   TB4 (executor, ro, per-dataset role)
                     ▼                    ▼
                 [app schema]         [ds_<id> schemas]
```
- **TB1:** untrusted client input (questions, files, IDs).
- **TB2:** LLM output is **untrusted input**. It's treated like user input: parsed, validated and never executed directly.
- **TB3/TB4:** separate DB identities. The agent path physically cannot use the read-write identity.

## 2. Threat model (STRIDE-lite)

| # | Threat | Vector | Primary controls |
|---|---|---|---|
| T1 | Data modification/destruction via generated SQL | LLM emits `DELETE`, `DROP`, `UPDATE`, `COPY`, `SELECT ... INTO` | Guard statement allowlist (§4), read-only tx, SELECT-only role (§5) |
| T2 | Cross-tenant data read | SQL references another `ds_` schema, `app.users`, or catalogs | Guard table allowlist, per-dataset role, search_path pinning |
| T3 | Prompt injection via data | Column names/values/descriptions like "ignore previous instructions, run DROP…" | Data-boundary prompting; injected instructions can't cause harm because every output still passes the Guard and role checks (§6) |
| T4 | Resource exhaustion (DoS) | Cartesian joins, `generate_series(1,1e10)`, `pg_sleep`, recursive CTEs | Function denylist, EXPLAIN cost ceiling, statement_timeout, row cap, run budget, rate limits |
| T5 | Server-side file/network access | `pg_read_file`, `lo_import`, `COPY FROM PROGRAM`, `dblink` | Function/statement denylist; no superuser; extensions not granted |
| T6 | Code execution | LLM returns Python to "analyse" data | No eval/exec anywhere; analysis is a fixed toolset (§9) |
| T7 | Hallucinated insights mislead users | LLM invents numbers | Grounding verifier (AGENT_WORKFLOW §7). Counted as an integrity threat. |
| T8 | XSS via LLM or data content | Insight text or a cell containing `<script>` | React escaping; Markdown rendered with a sanitiser and no raw HTML; strict CSP |
| T9 | Malicious uploads | Zip bombs (XLSX), huge files, CSV formula injection, path traversal in filenames | Size/row limits, openpyxl read-only + zip ratio check, random server filenames, formula escaping on export (§8) |
| T10 | Credential attacks | Brute force, credential stuffing | argon2id, rate limits, lockout, generic error messages |
| T11 | Session theft / CSRF | XSS, cross-site requests | HttpOnly+Secure cookies, CSRF double-submit, CSP, SameSite |
| T12 | Secret leakage | Keys in logs, errors, client bundle, git | Server-only env, log redaction, sanitised DB errors, secret scanning in CI |
| T13 | IDOR | Guessing UUIDs of others' runs/reports | Owner-scoped queries in every service method; 404 on foreign IDs |
| T14 | LLM cost abuse | Scripted runs | Per-user daily budget, concurrency limit |

## 3. Layered controls for analytical SQL (summary)

| Layer | Control | Stops |
|---|---|---|
| L1 | Prompt rules (SELECT only, schema-only columns) | Most mistakes. **Not relied on.** |
| L2 | **SQL Guard** (SQLGlot AST validation) | T1, T2, T4, T5 at the syntax/semantic level |
| L3 | **EXPLAIN cost gate** | T4 (expensive but valid queries) |
| L4 | **Executor session**: `SET ROLE ds_<id>_r`, `BEGIN READ ONLY`, `search_path`, `statement_timeout`, `idle_in_transaction_session_timeout`, row cap | T1, T2, T4 even if L2 has a bug |
| L5 | **DB privileges**: reader role has only USAGE + SELECT on one schema; no `pg_read_server_files`, `pg_execute_server_program`, `CREATE`, `TEMP` | T1, T2, T5 at the engine level |

A test (TESTING_STRATEGY §5) disables L2 and runs the adversarial suite directly against L4/L5 to prove the lower layers hold on their own.

## 4. SQL Guard specification

> **As built (Phases 5–6): see [SQL_SAFETY.md](SQL_SAFETY.md)** for the authoritative
> validation pipeline, error taxonomy, retry policy, cost gate, cancellation and test
> matrix. Deviations from the design below, decided during implementation:
> §4.1 — a bare trailing `;` is tolerated (models emit it; fuzzing proves a tail only
> passes when it parses to nothing). §4.2 — recursive CTEs, the join cap (6) and the
> subquery-depth cap (4) are enforced as designed since Phase 6. §4.3 — **all** table
> functions are rejected (stricter than the design's `unnest` exception). §4.5 — the
> function policy is hybrid: SQLGlot-typed functions pass, untyped ones need a small
> allowlist, and a denylist regex blocks the server surface even when typed. §4.6 —
> cost control is the EXPLAIN gate + statement timeout (no per-query EXPLAIN output in
> results). Unsafe queries and permission errors are never retried (D51).

`validate(sql: str, catalog: DatasetCatalog, policy: GuardPolicy) -> GuardResult`, a pure function with no I/O.

```python
class GuardResult(BaseModel):
    accepted: bool
    normalized_sql: str | None      # emitted via sqlglot for dialect="postgres"
    violations: list[Violation]     # {code, message, node_snippet}
    referenced_tables: list[str]
    referenced_columns: list[str]
```

### 4.1 Parsing
1. Reject input > 20,000 chars (`TOO_LONG`).
2. `sqlglot.parse(sql, dialect="postgres")` with `error_level=RAISE`. Parse failure → `PARSE_ERROR`.
3. Exactly **one** statement (`MULTIPLE_STATEMENTS`). Strip a single trailing semicolon. Comments are stripped by regenerating from the AST.

### 4.2 Statement allowlist
The root must be `exp.Select`, `exp.Union` / `exp.Intersect` / `exp.Except` (of selects), or a `WITH` whose body is one of these. Anything else → `STATEMENT_NOT_ALLOWED`.

Then a walk of **every** node in the tree; reject if any of these appear anywhere (including inside CTEs and subqueries):
`Insert, Update, Delete, Merge, Create, Drop, Alter, TruncateTable, Command (catch-all for unparsed commands like COPY/VACUUM/SET/GRANT), Into (SELECT … INTO), Lock (FOR UPDATE/SHARE), Transaction/Commit/Rollback, Set, Pragma, Use` → `FORBIDDEN_NODE:<type>`.

Recursive CTEs (`WITH RECURSIVE`) are rejected by default (`RECURSIVE_CTE`), since they rarely matter for business analysis and are a DoS vector.

### 4.3 Table and schema allowlist
- Every `exp.Table` must have no schema qualifier, or the qualifier must equal the dataset's `schema_name` (`FOREIGN_SCHEMA`). No catalog/db qualifiers.
- The table name must exist in the catalog (`UNKNOWN_TABLE`). CTE names are tracked and allowed as table references inside their scope.
- Explicitly blocked even if somehow present: `pg_*`, `information_schema.*`, `app.*`, `lg.*` (`SYSTEM_OBJECT`).
- Table-valued functions in FROM (`generate_series`, `unnest` of huge arrays, `json_to_recordset` over …) → only `unnest` is allowed, and only over a column reference.

### 4.4 Column validation
Using `sqlglot.optimizer.qualify` with a schema mapping built from the catalog: every column must resolve to a known table column, CTE output or select alias. Errors → `UNKNOWN_COLUMN` with a "did you mean" list (Levenshtein top-3 from the same table). This gives repair loops precise feedback.

### 4.5 Function policy
**Allowlist** approach (safer than a denylist): aggregates (`count, sum, avg, min, max, stddev*, variance*, percentile_cont, percentile_disc, mode, string_agg, array_agg, bool_and, bool_or`), window functions (`row_number, rank, dense_rank, ntile, lag, lead, first_value, last_value, cume_dist, percent_rank`), scalar (`coalesce, nullif, greatest, least, round, floor, ceil, abs, sign, power, sqrt, ln, log, exp, mod, cast, date_trunc, date_part, extract, to_char, to_date, age, make_date, now, current_date, lower, upper, trim, length, substring, position, replace, concat, split_part, left, right, case`), plus operators.

Any other function → `FUNCTION_NOT_ALLOWED:<name>`. Covered by this: `pg_sleep`, `pg_read_file`, `pg_ls_dir`, `lo_*`, `dblink*`, `set_config`, `current_setting`, `pg_terminate_backend`, `pg_cancel_backend`, `query_to_xml`, `txid_*`, `nextval/setval`, `version`, anything with schema qualification.

### 4.6 Structural limits
| Rule | Default | Code |
|---|---|---|
| Max joins | 6 | `TOO_MANY_JOINS` |
| Max subquery depth | 4 | `TOO_DEEP` |
| CROSS JOIN / comma join with no join predicate between non-trivial tables | rejected | `CARTESIAN_JOIN` |
| Max projected columns | 50 | `TOO_MANY_COLUMNS` |
| `SELECT *` | allowed only on single-table queries; rewritten to an explicit column list without `_row_id` | — |

### 4.7 Normalisation (rewrites)
- Outer `LIMIT`: if absent, inject `LIMIT policy.row_limit + 1` (the +1 detects truncation). If present and > limit, clamp it.
- Unqualified table names are qualified with the dataset schema (in addition to search_path).
- Output is regenerated with `sqlglot` (postgres dialect), so what runs is exactly what was validated.

### 4.8 Guard testing invariant
For every case in the adversarial corpus: `validate(...).accepted is False`. For every case in the benign corpus: `accepted is True` and `normalized_sql` executes. Property-based tests (Hypothesis) generate SQL fragments to fuzz the walk (TESTING_STRATEGY §5).

## 5. Database roles and session hardening

| Role | Login | Privileges |
|---|---|---|
| `sageboard_owner` | yes (migrations/bootstrap only) | owns `app`, `lg`; CREATEROLE |
| `sageboard_app` | yes (API service) | DML on `app.*`, `lg.*`; **no** access to `ds_*` |
| `sageboard_ingest` | yes (ingestion code path, separate pool) | CREATE on the database (to create `ds_*` schemas); owns those schemas |
| `sageboard_executor` | yes (Executor pool only) | **No direct privileges**; member of each `ds_<id>_r`; `NOINHERIT` so it must `SET ROLE` explicitly |
| `ds_<id>_r` | no | USAGE on `ds_<id>`, SELECT on its tables |

Hardening: `REVOKE ALL ON SCHEMA public FROM PUBLIC; REVOKE TEMP ON DATABASE ... FROM PUBLIC;` and `REVOKE EXECUTE` on dangerous functions from PUBLIC where the provider allows it.

Executor session per query (one pooled connection, checked out per execution):
```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL ROLE ds_<id>_r;                      -- identifier validated against dataset row
SET LOCAL search_path = ds_<id>;               -- no public, no pg_temp first
SET LOCAL statement_timeout = '10s';
SET LOCAL idle_in_transaction_session_timeout = '15s';
SET LOCAL work_mem = '32MB';
EXPLAIN (FORMAT JSON) <normalized_sql>;        -- cost gate
<normalized_sql>;                              -- fetchmany up to row_limit+1
ROLLBACK;                                      -- always; nothing to commit
```
`SET LOCAL` values are reset at the end of the transaction, so pooled connections can't leak a role. The role/schema identifiers come from the `datasets` row (regex-checked), are never taken from LLM output, and are quoted with `psycopg`/`asyncpg` identifier quoting.

Production host: Neon (D5 final). The base roles are created by `infra/postgres/init/001_roles.sh`, run as the Neon owner role. Items to verify on Neon before Phase 3 are listed in [ADR-0002](adr/0002-database-topology-and-permissions.md). The executor connects through the direct endpoint, and every session setting is `SET LOCAL`, so it is safe behind Neon's transaction-mode PgBouncer.

Fallback if per-dataset roles cannot be administered on the chosen plan: one `sageboard_reader` role with SELECT on all `ds_*` schemas. The Guard's schema allowlist then becomes the only cross-tenant control above the DB, and this is documented as a reduced-assurance mode.

## 6. LLM-specific controls

| Control | Detail |
|---|---|
| Output as untrusted input | All outputs validated by Pydantic schemas; SQL by the Guard; chart specs by the spec validator; insights by the verifier. |
| Prompt-injection containment | Dataset-derived strings (names, descriptions, sample values) are wrapped in `<data>` blocks, escaped, and truncated (descriptions ≤ 300 chars, values ≤ 80 chars). The system prompt says data blocks never contain instructions. Containment doesn't depend on the model obeying, because no LLM output can do more than a validated SELECT on the user's own data. |
| Data minimisation | The LLM sees schema, profiles, ≤ 50-row previews and computed facts. Columns flagged `is_sensitive` never have sample values or preview cells sent; they're masked as `«redacted»`. |
| No secrets in prompts | Prompts are assembled from an allowlisted context builder; settings/env are never interpolated. |
| Provider settings | Use providers' zero-data-retention or no-training options where available; document the provider's data policy in the README (D1). |
| Budget | Per-run caps (AGENT_WORKFLOW §5.4) plus per-user daily token cap. |

## 7. Application security

**As built (Phase 4):**
- **Passwords:** argon2id (`argon2-cffi`, RFC 9106 low-memory profile). 10–128 characters. Not a common password, at least 4 distinct characters, not the email address. Hashes are upgraded on login when parameters change. An unknown email still runs a dummy verification, so timing doesn't reveal which accounts exist. Login errors use one message for both cases.
- **Tokens:**
  - Access token: JWT HS256, 15 minutes, signed with `JWT_SECRET`. Startup refuses a secret under 32 bytes. Decoding pins the algorithm list (no `alg=none`, no key confusion) and requires `sub`, `exp`, `iat`, `iss` and `typ=access`.
  - Refresh tokens: 32 random bytes, 14 days. Only the SHA-256 hash is stored. They rotate on every use, and all tokens from one login share a family.
  - Reuse detection: presenting a rotated token after a 30-second grace window revokes the whole family and writes `auth.refresh_reuse` to the audit log. The grace window covers two tabs refreshing at the same moment.
  - Sign-out revokes the family.
- **Cookies:** `sb_session` and `sb_refresh` are HttpOnly; `sb_refresh` is only ever sent to `/api/v1/auth`. `SameSite=Lax` by default; `Secure` is automatic in production. `COOKIE_SAMESITE=none` requires Secure, and startup refuses it otherwise. In production, startup also refuses `COOKIE_SECURE=false` and `AUTH_MODE=demo`.
- **CSRF:** double-submit. The `sb_csrf` cookie must equal the `X-CSRF-Token` header on every POST/PUT/PATCH/DELETE, compared in constant time. The token is also returned in the response body, so cross-site frontends never need to read another site's cookie. Register, login and refresh are exempt (see API_SPECIFICATION §1.1 for why refresh is safe).
- **Rate limits:** per-process sliding windows for login (per IP + email and per IP), registration (per IP) and uploads (per user). Over the limit returns 429 with `Retry-After`.
- **Authorisation:**
  - Every service method takes the signed-in user, and every query filters by `owner_id`, so another user's resource is a 404, never a 403.
  - `tests/integration/test_ownership.py` walks every route with an id in its path, using a second user. It fails if a new route can't be checked.
  - Lists and filters given someone else's ids return nothing.
  - Each user gets their own copy of the sample dataset in their own schema.
- **Audit log** (`app.audit_log`): register, login, failed login, logout, refresh-token reuse, dataset create and delete.
- **Input validation:** Pydantic models reject unknown fields (`extra="forbid"`) and enforce lengths. UUIDs are typed. Enum filters are validated. Cursors are opaque and validated.
- **Error hygiene:** connection-level database failures return `503 DATABASE_UNAVAILABLE` with no driver text, host, user or SQL (tested). Unexpected errors return a generic 500, with details only in the log under the request id.
- **CORS:** explicit origin allowlist with credentials. The allowed headers include `X-CSRF-Token`; `Retry-After` is exposed. Other origins get no CORS headers (tested).
- **Frontend:** all data is fetched client-side with `credentials: "include"`. The app area waits for `/auth/me` before rendering. A session change (sign-in, sign-out or expiry) triggers a full page load, so no client-side state from the previous session survives. After sign-in the app only redirects to same-app paths (`/app…`), never another site.

**Planned:**
- Content Security Policy and other security headers (Phase 13).
- Password change and account deletion (deletion must also drop the user's warehouse schemas).
- Email verification and password reset.
- Rate limits shared across instances.

## 8. File upload security

**As built (Phase 3, CSV only — D28):**
- Limits (env-configurable): 25 MB (`UPLOAD_MAX_BYTES`), 1,000,000 rows, 200 columns, 10,000 characters per cell. The size limit is enforced **while streaming** to disk, so an oversized upload never fully lands (`413 FILE_TOO_LARGE`), and the partial file is deleted.
- Only `.csv` is accepted. Excel files get an explicit “save as CSV UTF-8” message (`415`). Content checks: NUL bytes → `BINARY_FILE`; strict UTF-8 (BOM allowed) → `ENCODING`; a strict CSV parser, so an unclosed quote is an error rather than silently swallowing the rest of the file.
- Storage: a random 256-bit token names the file (`<token>.upload`) in a private directory (`0700`). The file is created with `O_EXCL` and mode `0600`. Tokens are regex-checked and the resolved path must stay inside the upload directory (traversal tests). The client's filename is display-only: base name kept, control characters stripped, 200 chars max.
- Lifecycle: the file is deleted after a successful load, a failed load or dataset deletion. Unreviewed uploads older than `UPLOAD_TTL_MINUTES` (60) are swept at startup.
- Loading: values are parsed in Python to typed objects and sent with `COPY` (asyncpg `copy_records_to_table`), so cell content is never interpolated into SQL. Table and column names are normalised and validated against `^[a-z_][a-z0-9_]{0,62}$`, then quoted.
- The whole load (schema, role, table, COPY, grants, catalog) is one transaction. Any failure leaves no schema, role or rows behind (tested).

**Planned:** XLSX (openpyxl `read_only=True, data_only=True` after a zip size/ratio check, reject > 100:1 or > 500 MB uncompressed, ≤ 10 sheets; macros and external links ignored), MIME/magic-byte sniffing, and moving ingestion to a background worker.
- **CSV export (Phase 12):** cells starting with `= + - @ \t \r` are prefixed with `'` (formula-injection mitigation).

## 9. No code execution policy
- The codebase has no `eval`, `exec`, `compile`, `subprocess`, `os.system` or `pickle.loads` on dynamic input. A CI check enforces this (ruff `S` rules: S102, S307, S602–S607, S301, plus a custom grep gate on `app/`).
- The analysis engine is a fixed set of Python functions with typed parameters. The LLM can only *choose* a function and pass column names that are validated against the result columns.
- Chart rendering is declarative (`ChartSpec` → Recharts). The LLM never produces JSX, HTML or JS.

## 10. Secrets and configuration
- Secrets exist only in platform env vars and local `.env` (gitignored; `.env.example` committed with placeholders).
- `gitleaks` runs in CI and pre-commit.
- The frontend only gets `NEXT_PUBLIC_API_URL`. No LLM key ever reaches the browser.
- Structlog processor redacts keys matching `/(password|secret|token|key|authorization|cookie)/i`. Dataset row values aren't logged.

## 11. Auditing and monitoring
- `audit_log` records auth events, dataset create/delete, account deletion, and every Guard rejection (with violation codes; SQL text is truncated to 2k).
- Alert-worthy signals (logged at WARN with a counter): repeated `FORBIDDEN_NODE`/`FOREIGN_SCHEMA` rejections from one user (possible probing), refresh-token reuse, lockouts.

## 12. Security acceptance criteria (gate for release)
1. The adversarial SQL corpus (≥ 150 cases) is 100% rejected by the Guard, and with the Guard bypassed, 100% blocked or harmless at L4/L5.
2. The cross-tenant test matrix passes for every resource route.
3. `ruff S`, `gitleaks`, `pip-audit` and `pnpm audit --prod` (high/critical) are clean or have documented exceptions.
4. The prompt-injection test set (malicious column names/values/descriptions) causes no Guard bypass and no instruction-following that changes the run's scope.
5. The CSP is present in production responses (Playwright check).
