"""SQL Guard: decides whether model-written SQL may run (docs/security/SECURITY.md).

The Guard is a pure function. It never talks to a database. It parses the SQL with
SQLGlot (PostgreSQL dialect) and accepts only a single read-only query over the
current dataset's tables:

1. exactly one statement, and it is a ``SELECT`` (CTEs and ``UNION``/``INTERSECT``/
   ``EXCEPT`` allowed);
2. no data-changing or session-changing node anywhere in the tree (``INSERT``,
   ``UPDATE``, ``DELETE``, ``MERGE``, DDL, ``COPY``, ``SET``, transactions, ``GRANT``,
   ``SELECT … INTO``, ``FOR UPDATE``…), including inside CTEs;
3. every table is a table of this dataset (unqualified, or qualified with the dataset's
   own schema); no ``pg_catalog``, ``information_schema``, ``app`` or other schemas;
4. every column exists (SQLGlot's qualifier resolves each column against the real
   catalog), with close-match suggestions when it doesn't;
5. functions SQLGlot doesn't recognise must be on a small allowlist, and anything
   that touches the server (``pg_*``, ``lo_*``, ``dblink``, ``set_config``…) is refused;
6. the outer ``LIMIT`` is a literal no greater than the row cap; it is added when
   missing. The cap is set to ``max_rows + 1`` so the executor can tell a result was
   truncated.

The Guard is the first line of defence, not the only one: the executor still runs as a
dataset-specific read-only role inside a ``READ ONLY`` transaction with a timeout.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp
from sqlglot.errors import OptimizeError, ParseError, SqlglotError
from sqlglot.optimizer.qualify import qualify

from app.agent.state import GuardViolation

MAX_SQL_CHARS = 20_000
MAX_JOINS = 6
MAX_SUBQUERY_DEPTH = 4

_FORBIDDEN_NODE_NAMES = (
    "Insert",
    "Update",
    "Delete",
    "Merge",
    "Create",
    "Drop",
    "Alter",
    "AlterTable",
    "TruncateTable",
    "Command",
    "Copy",
    "Set",
    "SetItem",
    "Transaction",
    "Commit",
    "Rollback",
    "Grant",
    "Revoke",
    "Use",
    "Pragma",
    "LoadData",
    "Analyze",
    "Cache",
    "Uncache",
    "Refresh",
    "Describe",
    "Show",
    "Comment",
    "Kill",
)
FORBIDDEN_NODES: tuple[type[exp.Expression], ...] = tuple(
    getattr(exp, name) for name in _FORBIDDEN_NODE_NAMES if hasattr(exp, name)
)

# Functions SQLGlot parses as "Anonymous" (it has no typed node for them) that are
# safe for analytics. Typed functions (SUM, DATE_TRUNC, EXTRACT, ROUND…) are allowed.
ALLOWED_UNTYPED_FUNCTIONS = frozenset(
    {
        "age",
        "btrim",
        "date_part",
        "initcap",
        "justify_days",
        "justify_interval",
        "make_date",
        "make_interval",
        "make_timestamp",
        "percent_rank",
        "regexp_replace",
        "split_part",
        "to_number",
        "trunc",
        "width_bucket",
        "isfinite",
        "date_bin",
        "cume_dist",
        "mode",
        "bool_and",
        "bool_or",
        "every",
        "nullif",
        "to_char",
        "string_agg",
    }
)
_DANGEROUS_FUNCTION = re.compile(
    r"^(pg_|lo_|dblink|set_config|current_setting|query_to_xml|table_to_xml|"
    r"cursor_to_xml|database_to_xml|schema_to_xml|txid_|inet_|has_.*privilege|"
    r"version$|current_version$|current_user$|current_role$|current_schema|"
    r"current_database$|current_catalog$|session_user$|user$|nextval$|setval$|"
    r"currval$|lastval$|generate_series$|repeat$|crypt$|gen_random|uuid$)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class GuardResult:
    ok: bool
    violations: list[GuardViolation] = field(default_factory=list)
    normalized_sql: str | None = None
    tables: list[str] = field(default_factory=list)
    limit_applied: int | None = None


@dataclass(frozen=True)
class GuardPolicy:
    dataset_schema: str
    # table -> {column -> data type}
    tables: dict[str, dict[str, str]]
    max_rows: int


def _violation(code: str, message: str) -> GuardResult:
    return GuardResult(ok=False, violations=[GuardViolation(code=code, message=message)])


def _function_name(func: exp.Func) -> str:
    if isinstance(func, exp.Anonymous):
        return str(func.name)
    return func.sql_name()


def validate_sql(sql: str, policy: GuardPolicy) -> GuardResult:
    """Validate ``sql`` for ``policy``; return the normalised SQL to execute if safe."""
    parsed = _parse_single_select(sql)
    if isinstance(parsed, GuardResult):
        return parsed
    root = parsed
    used: list[str] = []
    violations = [
        *_statement_violations(root),
        *_cartesian_violations(root),
        *_table_violations(root, policy, used),
        *_function_violations(root),
    ]
    if violations:
        return GuardResult(ok=False, violations=_dedupe(violations))
    column_violation = _check_columns(root, policy)
    if column_violation:
        return GuardResult(ok=False, violations=[column_violation])
    applied = _apply_row_cap(root, policy.max_rows + 1)
    if isinstance(applied, GuardResult):
        return applied
    normalized = root.sql(dialect="postgres", comments=False)
    return GuardResult(ok=True, normalized_sql=normalized, tables=used, limit_applied=applied)


def _parse_single_select(sql: str) -> exp.Expression | GuardResult:
    text = (sql or "").strip()
    if not text:
        return _violation("EMPTY_SQL", "The query is empty.")
    if len(text) > MAX_SQL_CHARS:
        return _violation("TOO_LONG", f"The query is longer than {MAX_SQL_CHARS} characters.")
    try:
        statements = [s for s in sqlglot.parse(text, read="postgres") if s is not None]
    except SqlglotError as exc:  # ParseError and tokenizer errors
        errors = exc.errors if isinstance(exc, ParseError) else []
        first = errors[0]["description"] if errors else str(exc)
        return _violation("SYNTAX_ERROR", f"The SQL could not be parsed: {first}"[:300])
    if len(statements) != 1:
        return _violation(
            "MULTIPLE_STATEMENTS", "Exactly one statement is allowed (found more than one)."
        )
    root = statements[0]
    if not isinstance(root, exp.Select | exp.SetOperation):
        return _violation("NOT_A_SELECT", f"Only SELECT queries are allowed (got {root.key}).")
    return root


def _statement_violations(root: exp.Expression) -> list[GuardViolation]:
    out = []
    if any(w.args.get("recursive") for w in root.find_all(exp.With)):
        out.append(
            GuardViolation(
                code="RECURSIVE_CTE",
                message="Recursive CTEs are not allowed; compute per-row values with joins or window functions.",
            )
        )
    joins = sum(1 for _ in root.find_all(exp.Join))
    if joins > MAX_JOINS:
        out.append(
            GuardViolation(
                code="TOO_MANY_JOINS",
                message=f"The query joins {joins} times (limit {MAX_JOINS}); aggregate in steps instead.",
            )
        )
    depth = _subquery_depth(root)
    if depth > MAX_SUBQUERY_DEPTH:
        out.append(
            GuardViolation(
                code="TOO_DEEP",
                message=f"Subqueries are nested {depth} levels deep (limit {MAX_SUBQUERY_DEPTH}); flatten with CTEs.",
            )
        )
    forbidden = next((n for n in root.walk() if isinstance(n, FORBIDDEN_NODES)), None)
    if forbidden is not None:
        out.append(
            GuardViolation(
                code="FORBIDDEN_STATEMENT",
                message=f"{forbidden.key.upper()} is not allowed in an analysis query.",
            )
        )
    if root.find(exp.Into):
        out.append(GuardViolation(code="SELECT_INTO", message="SELECT … INTO is not allowed."))
    if root.find(exp.Lock):
        out.append(
            GuardViolation(code="LOCKING_CLAUSE", message="FOR UPDATE/SHARE is not allowed.")
        )
    return out


def _is_true_literal(node: exp.Expression | None) -> bool:
    return isinstance(node, exp.Boolean) and bool(node.this)


def _linked_by_where(select: exp.Select) -> bool:
    """True when WHERE equates columns of two different tables (an old-style comma join)."""
    where = select.args.get("where")
    if where is None:
        return False
    for eq in where.find_all(exp.EQ):
        left, right = eq.left, eq.right
        if (
            isinstance(left, exp.Column)
            and isinstance(right, exp.Column)
            and left.table != right.table
        ):
            return True
    return False


def _cartesian_violations(root: exp.Expression) -> list[GuardViolation]:
    """Reject a join of two base tables that has no join condition.

    A CROSS JOIN against a subquery or CTE (e.g. a one-row grand total) stays allowed: it is
    the usual way to compute a share of the total and cannot multiply a large table by another.
    """
    ctes = {c.alias_or_name for c in root.find_all(exp.CTE)}

    def is_base_table(node: exp.Expression | None) -> bool:
        return isinstance(node, exp.Table) and node.name not in ctes

    for select in root.find_all(exp.Select):
        source = select.args.get("from_") or select.args.get("from")
        left_is_base = source is not None and is_base_table(source.this)
        for join in select.args.get("joins") or []:
            right_is_base = is_base_table(join.this)
            has_condition = join.args.get("using") or (
                join.args.get("on") is not None and not _is_true_literal(join.args["on"])
            )
            if (
                right_is_base
                and left_is_base
                and not has_condition
                and not _linked_by_where(select)
            ):
                return [
                    GuardViolation(
                        code="CARTESIAN_JOIN",
                        message=(
                            f"Table “{join.this.name}” is joined without a join condition, which "
                            "pairs every row with every row. Join on a key, e.g. "
                            "orders.customer_id = customers.customer_id."
                        ),
                    )
                ]
            left_is_base = left_is_base or right_is_base
    return []


def _subquery_depth(root: exp.Expression) -> int:
    deepest = 0
    for select in root.find_all(exp.Select):
        level, node = 1, select.parent
        while node is not None:
            if isinstance(node, exp.Select):
                level += 1
            node = node.parent
        deepest = max(deepest, level)
    return deepest


def _table_violations(
    root: exp.Expression, policy: GuardPolicy, used: list[str]
) -> list[GuardViolation]:
    """Every table must belong to the dataset; collects the tables used into ``used``."""
    out = []
    cte_names = {cte.alias_or_name.lower() for cte in root.find_all(exp.CTE)}
    known = {name.lower(): name for name in policy.tables}
    for table in root.find_all(exp.Table):
        if not isinstance(table.this, exp.Identifier):
            out.append(
                GuardViolation(
                    code="FORBIDDEN_FUNCTION", message="Table functions are not allowed in FROM."
                )
            )
            continue
        name, schema = table.name.lower(), (table.db or "").lower()
        if table.catalog:
            out.append(
                GuardViolation(
                    code="FORBIDDEN_SCHEMA", message="Database-qualified names are not allowed."
                )
            )
        elif schema and schema != policy.dataset_schema.lower():
            out.append(
                GuardViolation(
                    code="FORBIDDEN_SCHEMA", message=f"Schema “{table.db}” is outside this dataset."
                )
            )
        elif not schema and name in cte_names:
            continue
        elif name not in known:
            suggestion = difflib.get_close_matches(name, list(known), n=2)
            hint = f" Did you mean {', '.join(suggestion)}?" if suggestion else ""
            out.append(
                GuardViolation(
                    code="UNKNOWN_TABLE",
                    message=(
                        f"Table “{table.name}” does not exist. Available tables: "
                        f"{', '.join(sorted(policy.tables))}.{hint}"
                    ),
                )
            )
        else:
            if known[name] not in used:
                used.append(known[name])
            if schema:
                table.set("db", None)  # normalise: the executor pins search_path
    return out


def _function_violations(root: exp.Expression) -> list[GuardViolation]:
    out = []
    for func in root.find_all(exp.Func):
        fname = _function_name(func)
        untyped_unknown = (
            isinstance(func, exp.Anonymous) and fname.lower() not in ALLOWED_UNTYPED_FUNCTIONS
        )
        if _DANGEROUS_FUNCTION.match(fname) or untyped_unknown:
            out.append(
                GuardViolation(
                    code="FORBIDDEN_FUNCTION", message=f"Function {fname}() is not allowed."
                )
            )
    return out


def _apply_row_cap(root: exp.Expression, cap: int) -> int | GuardResult:
    """Make the outer LIMIT a literal ≤ ``cap`` (added when missing); returns the limit."""
    limit = root.args.get("limit")
    applied = cap
    if limit is not None:
        value = limit.expression if isinstance(limit, exp.Limit) else None
        if not isinstance(value, exp.Literal) or not value.is_int:
            return _violation("NON_LITERAL_LIMIT", "LIMIT must be a whole number.")
        requested = int(value.this)
        if requested <= cap:
            applied = requested
        else:
            limit.set("expression", exp.Literal.number(cap))
    else:
        root.set("limit", exp.Limit(expression=exp.Literal.number(cap)))
    offset = root.args.get("offset")
    if offset is not None:
        value = offset.expression
        if not isinstance(value, exp.Literal) or not value.is_int:
            return _violation("NON_LITERAL_LIMIT", "OFFSET must be a whole number.")
    return applied


def _check_columns(root: exp.Expression, policy: GuardPolicy) -> GuardViolation | None:
    schema: dict[str, object] = {name: dict(cols) for name, cols in policy.tables.items()}
    try:
        qualify(
            root.copy(),
            schema=schema,
            dialect="postgres",
            validate_qualify_columns=True,
            identify=False,
        )
    except OptimizeError as exc:
        message = str(exc).split(". Line:")[0]
        missing = re.search(r"(?:Unknown column: |Column ')([\w.]+)", message)
        if missing:
            reference = missing.group(1)
            return GuardViolation(
                code="UNKNOWN_COLUMN", message=_unknown_column_message(root, policy, reference)
            )
        if "mbiguous" in message:
            return GuardViolation(code="AMBIGUOUS_COLUMN", message=message[:300])
        return GuardViolation(code="INVALID_REFERENCE", message=message[:300])
    except SqlglotError as exc:
        return GuardViolation(code="INVALID_REFERENCE", message=str(exc)[:300])
    return None


def _unknown_column_message(root: exp.Expression, policy: GuardPolicy, reference: str) -> str:
    column = reference.rsplit(".", maxsplit=1)[-1]
    aliases = {t.alias_or_name.lower(): t.name.lower() for t in root.find_all(exp.Table) if t.name}
    owner = None
    for col in root.find_all(exp.Column):
        if col.name.lower() == column.lower() and col.table:
            owner = aliases.get(col.table.lower(), col.table.lower())
            break
    holders = sorted(t for t, cols in policy.tables.items() if column.lower() in cols)
    if owner and owner in policy.tables:
        message = f"Table “{owner}” has no column “{column}”."
    else:
        message = f"Column “{column}” does not exist in the tables used."
    if holders:
        message += f" It exists in: {', '.join(holders)} (join that table to use it)."
    else:
        every = sorted({c for cols in policy.tables.values() for c in cols})
        close = difflib.get_close_matches(column.lower(), every, n=3)
        if close:
            message += f" Similar columns: {', '.join(close)}."
    return message


def _dedupe(violations: list[GuardViolation]) -> list[GuardViolation]:
    seen: set[tuple[str, str]] = set()
    unique = []
    for v in violations:
        if (v.code, v.message) not in seen:
            seen.add((v.code, v.message))
            unique.append(v)
    return unique
