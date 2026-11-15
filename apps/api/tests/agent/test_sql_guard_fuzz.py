"""Property-based fuzzing of the SQL Guard (Hypothesis).

The fixed corpus in test_sql_guard.py proves known attacks are rejected. These
properties go further: *generated* inputs must never make the Guard crash, accept a
write, accept a second statement, or accept an unknown table — whatever the spelling,
casing, whitespace or comments. ``derandomize=True`` keeps CI deterministic.
"""

from __future__ import annotations

import sqlglot
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlglot import exp

from app.agent.tools.errors import UNSAFE_GUARD_CODES
from app.agent.tools.schema import SchemaTools
from app.agent.tools.sql_guard import GuardPolicy, validate_sql
from tests.agent.fakes import shop_catalog

POLICY: GuardPolicy = SchemaTools(shop_catalog()).guard_policy(max_rows=500)
FUZZ = settings(
    max_examples=150, deadline=None, derandomize=True, suppress_health_check=[HealthCheck.too_slow]
)

TABLES = sorted(POLICY.tables)
COLUMNS = {t: sorted(POLICY.tables[t]) for t in TABLES}

DML = st.sampled_from(
    [
        "DELETE FROM {t}",
        "UPDATE {t} SET {c} = NULL",
        "INSERT INTO {t} ({c}) VALUES (1)",
        "DROP TABLE {t}",
        "TRUNCATE {t}",
        "ALTER TABLE {t} ADD COLUMN zz int",
        "CREATE TABLE zz AS SELECT * FROM {t}",
        "GRANT SELECT ON {t} TO PUBLIC",
        "COPY {t} TO '/tmp/x'",
        "SET ROLE postgres",
    ]
)


def mangle(statement: str, spaces: list[int], upper: bool, comment: str) -> str:
    """Random casing, extra whitespace and an inline comment — same meaning."""
    text = statement.upper() if upper else statement.lower()
    words = text.split(" ")
    for i in sorted(spaces, reverse=True):
        words.insert(i % (len(words) + 1), " ")
    out = " ".join(words)
    if comment:
        out = f"/* {comment} */ {out}"
    return out


comments = st.text(
    alphabet=st.characters(exclude_characters="*/;", exclude_categories=["Cs"]), max_size=20
)


@FUZZ
@given(
    template=DML,
    table=st.sampled_from(TABLES),
    upper=st.booleans(),
    spaces=st.lists(st.integers(0, 12), max_size=4),
    comment=comments,
)
def test_writes_are_rejected_whatever_the_spelling(
    template: str, table: str, upper: bool, spaces: list[int], comment: str
) -> None:
    sql = mangle(template.format(t=table, c=COLUMNS[table][0]), spaces, upper, comment)
    result = validate_sql(sql, POLICY)
    assert not result.ok, sql


@FUZZ
@given(
    table=st.sampled_from(TABLES),
    tail=st.text(max_size=40),
    upper=st.booleans(),
)
def test_a_second_statement_never_executes(table: str, tail: str, upper: bool) -> None:
    """Anything after a semicolon is rejected — unless it parses to *nothing* (a bare
    trailing ';', whitespace or a comment), which models emit on benign SQL all the time.
    Acceptance therefore implies the tail contributed no executable statement."""
    benign = f"SELECT COUNT(*) FROM {table}"
    sql = f"{benign.upper() if upper else benign}; {tail}"
    result = validate_sql(sql, POLICY)
    if result.ok:
        _assert_safe_normalized(result.normalized_sql, result.tables)
        tail_statements = [s for s in sqlglot.parse(tail, read="postgres") if s is not None]
        assert tail_statements == [], sql


@FUZZ
@given(name=st.from_regex(r"[A-Za-z_][A-Za-z0-9_]{0,20}", fullmatch=True))
def test_only_catalog_tables_are_readable(name: str) -> None:
    result = validate_sql(f"SELECT * FROM {name}", POLICY)
    if result.ok:
        assert name.lower() in POLICY.tables, name
    else:
        assert result.violations, name


@FUZZ
@given(garbage=st.text(max_size=120))
def test_arbitrary_text_never_crashes_the_guard_or_slips_through(garbage: str) -> None:
    result = validate_sql(garbage, POLICY)  # must never raise
    if result.ok:
        _assert_safe_normalized(result.normalized_sql, result.tables)


@FUZZ
@given(
    table=st.sampled_from(TABLES),
    agg=st.sampled_from(["COUNT(*)", "SUM(1)", "MIN({c})", "MAX({c})"]),
    group=st.booleans(),
    limit=st.integers(min_value=-5, max_value=10_000_000),
    use_limit=st.booleans(),
)
def test_accepted_queries_stay_safe_after_normalisation(
    table: str, agg: str, group: bool, limit: int, use_limit: bool
) -> None:
    """Accepted ⇒ the *normalised* SQL re-validates, is one SELECT, reads only catalog
    tables, and carries a LIMIT within the cap (idempotence of the Guard)."""
    first = COLUMNS[table][0]
    sql = f"SELECT {f'{first}, ' if group else ''}{agg.format(c=first)} AS v FROM {table}"
    if group:
        sql += f" GROUP BY {first}"
    if use_limit:
        sql += f" LIMIT {limit}"
    result = validate_sql(sql, POLICY)
    if not result.ok:
        assert use_limit and limit < 0, (sql, result.violations)  # only negative limits fail
        return
    _assert_safe_normalized(result.normalized_sql, result.tables)


def _assert_safe_normalized(normalized: str | None, tables: list[str]) -> None:
    assert normalized is not None
    again = validate_sql(normalized, POLICY)
    assert again.ok, (normalized, again.violations)
    statements = sqlglot.parse(normalized, read="postgres")
    assert len(statements) == 1
    assert isinstance(statements[0], exp.Select | exp.SetOperation)
    assert set(tables) <= set(POLICY.tables)
    limit = statements[0].args.get("limit")
    assert limit is not None and int(limit.expression.this) <= POLICY.max_rows + 1


def test_unsafe_guard_codes_match_real_guard_codes() -> None:
    """The no-retry set must name codes the Guard actually emits (typo protection)."""
    emitted = {
        "EMPTY_SQL",
        "TOO_LONG",
        "SYNTAX_ERROR",
        "MULTIPLE_STATEMENTS",
        "NOT_A_SELECT",
        "FORBIDDEN_STATEMENT",
        "SELECT_INTO",
        "LOCKING_CLAUSE",
        "FORBIDDEN_SCHEMA",
        "UNKNOWN_TABLE",
        "FORBIDDEN_FUNCTION",
        "UNKNOWN_COLUMN",
        "AMBIGUOUS_COLUMN",
        "INVALID_REFERENCE",
        "NON_LITERAL_LIMIT",
        "REPEATED_QUERY",
    }
    assert emitted >= UNSAFE_GUARD_CODES
