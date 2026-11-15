"""SQL Guard: adversarial corpus (must reject) and benign corpus (must accept)."""

from __future__ import annotations

import pytest

from app.agent.tools.schema import SchemaTools
from app.agent.tools.sql_guard import GuardPolicy, validate_sql
from tests.agent.fakes import shop_catalog

POLICY: GuardPolicy = SchemaTools(shop_catalog()).guard_policy(max_rows=500)
SCHEMA = POLICY.dataset_schema

ADVERSARIAL: list[tuple[str, str]] = [
    ("", "EMPTY_SQL"),
    ("DELETE FROM orders", "NOT_A_SELECT"),
    ("UPDATE orders SET status = 'x'", "NOT_A_SELECT"),
    ("INSERT INTO orders (order_id) VALUES (1)", "NOT_A_SELECT"),
    ("DROP TABLE orders", "NOT_A_SELECT"),
    ("TRUNCATE orders", "NOT_A_SELECT"),
    ("ALTER TABLE orders ADD COLUMN x int", "NOT_A_SELECT"),
    ("CREATE TABLE x AS SELECT * FROM orders", "NOT_A_SELECT"),
    ("COPY orders TO '/tmp/out.csv'", "NOT_A_SELECT"),
    ("SET ROLE sageboard_owner", "NOT_A_SELECT"),
    ("GRANT SELECT ON orders TO public", "NOT_A_SELECT"),
    ("BEGIN", "NOT_A_SELECT"),
    ("SELECT 1; DROP TABLE orders", "MULTIPLE_STATEMENTS"),
    ("SELECT 1; SELECT 2", "MULTIPLE_STATEMENTS"),
    ("WITH d AS (DELETE FROM orders RETURNING *) SELECT * FROM d", "FORBIDDEN_STATEMENT"),
    ("SELECT * INTO stolen FROM orders", "SELECT_INTO"),
    ("SELECT * FROM orders FOR UPDATE", "LOCKING_CLAUSE"),
    ("SELECT * FROM pg_catalog.pg_roles", "FORBIDDEN_SCHEMA"),
    ("SELECT * FROM information_schema.tables", "FORBIDDEN_SCHEMA"),
    ("SELECT email FROM app.users", "FORBIDDEN_SCHEMA"),
    ("SELECT * FROM ds_ffffffffffffffff.orders", "FORBIDDEN_SCHEMA"),
    ("SELECT * FROM otherdb.public.orders", "FORBIDDEN_SCHEMA"),
    ("SELECT * FROM pg_shadow", "UNKNOWN_TABLE"),
    ("SELECT * FROM users", "UNKNOWN_TABLE"),
    ("SELECT pg_sleep(30)", "FORBIDDEN_FUNCTION"),
    ("SELECT pg_read_file('/etc/passwd')", "FORBIDDEN_FUNCTION"),
    ("SELECT set_config('role', 'x', false)", "FORBIDDEN_FUNCTION"),
    ("SELECT current_setting('server_version')", "FORBIDDEN_FUNCTION"),
    ("SELECT version()", "FORBIDDEN_FUNCTION"),
    ("SELECT current_user", "FORBIDDEN_FUNCTION"),
    ("SELECT dblink('host=x', 'select 1')", "FORBIDDEN_FUNCTION"),
    ("SELECT lo_import('/etc/passwd')", "FORBIDDEN_FUNCTION"),
    ("SELECT nextval('seq')", "FORBIDDEN_FUNCTION"),
    ("SELECT repeat('x', 100000000)", "FORBIDDEN_FUNCTION"),
    ("SELECT * FROM generate_series(1, 1000000000)", "FORBIDDEN_FUNCTION"),
    ("SELECT order_id FROM orders WHERE status = 'a' /* ; DROP TABLE orders */", "OK_COMMENT"),
    ("SELECT ctid, xmin FROM orders", "UNKNOWN_COLUMN"),
    ("SELECT o.region FROM orders AS o", "UNKNOWN_COLUMN"),
    ("SELECT revenue FROM orders", "UNKNOWN_COLUMN"),
    ("SELECT * FROM orders LIMIT ALL", "NON_LITERAL_LIMIT"),
    ("SELECT * FROM orders LIMIT (SELECT 10)", "NON_LITERAL_LIMIT"),
    ("SELEC * FROM orders", "SYNTAX_ERROR"),
    (
        "WITH RECURSIVE t AS (SELECT 1 AS n UNION ALL SELECT n + 1 FROM t WHERE n < 10) SELECT * FROM t",
        "RECURSIVE_CTE",
    ),
    (
        "SELECT COUNT(*) FROM orders o0 "
        + " ".join(f"JOIN orders o{i} ON o{i}.order_id = o{i - 1}.order_id" for i in range(1, 8)),
        "TOO_MANY_JOINS",
    ),
    (
        "SELECT * FROM (SELECT * FROM (SELECT * FROM (SELECT * FROM (SELECT order_id FROM orders) a) b) c) d",
        "TOO_DEEP",
    ),
    ("x" * 20_001, "TOO_LONG"),
]


@pytest.mark.parametrize(("sql", "code"), ADVERSARIAL, ids=[c for _, c in ADVERSARIAL])
def test_adversarial_queries_are_rejected(sql: str, code: str) -> None:
    result = validate_sql(sql, POLICY)
    if code == "OK_COMMENT":
        # Comments are stripped from what executes, so the hidden DROP never runs.
        assert result.ok and result.normalized_sql and "DROP" not in result.normalized_sql
        return
    assert not result.ok, result.normalized_sql
    assert code in [v.code for v in result.violations], result.violations


BENIGN = [
    "SELECT COUNT(*) AS orders FROM orders",
    "SELECT COUNT(*) AS orders FROM orders;",  # a bare trailing semicolon is tolerated
    "SELECT status, COUNT(*) AS n FROM orders GROUP BY status ORDER BY n DESC",
    f"SELECT COUNT(*) FROM {SCHEMA}.orders",
    "SELECT DATE_TRUNC('month', order_date) AS month, COUNT(*) FROM orders GROUP BY 1 ORDER BY 1",
    "SELECT EXTRACT(YEAR FROM order_date) AS y, COUNT(*) FROM orders GROUP BY y",
    "SELECT TO_CHAR(order_date, 'YYYY-MM') AS m FROM orders",
    "WITH t AS (SELECT customer_id, COUNT(*) AS n FROM orders GROUP BY customer_id) SELECT AVG(n) FROM t",
    "SELECT c.region, SUM(oi.quantity * oi.unit_price) AS revenue FROM order_items oi "
    "JOIN orders o ON o.order_id = oi.order_id JOIN customers c ON c.customer_id = o.customer_id "
    "WHERE o.status <> 'cancelled' GROUP BY c.region",
    "SELECT status FROM orders UNION ALL SELECT region FROM customers",
    "SELECT COUNT(*) FILTER (WHERE status = 'cancelled')::numeric / NULLIF(COUNT(*), 0) AS rate FROM orders",
    "SELECT category, RANK() OVER (ORDER BY COUNT(*) DESC) FROM products GROUP BY category",
    "SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY quantity) FROM order_items",
    "SELECT STRING_AGG(DISTINCT category, ', ') FROM products",
    "SELECT CASE WHEN quantity > 3 THEN 'bulk' ELSE 'single' END AS kind, COUNT(*) FROM order_items GROUP BY 1",
    "SELECT order_id FROM orders ORDER BY order_date DESC LIMIT 10 OFFSET 5",
    "SELECT * FROM (SELECT status, COUNT(*) n FROM orders GROUP BY status) s WHERE n > 10",
    "SELECT * FROM (SELECT * FROM (SELECT order_id FROM orders) a) b",  # depth 3 ≤ 4
    "SELECT COUNT(*) FROM orders o JOIN order_items oi ON oi.order_id = o.order_id "
    "JOIN products p ON p.product_id = oi.product_id JOIN customers c ON c.customer_id = o.customer_id",
    "SELECT COALESCE(SUM(quantity), 0) FROM order_items WHERE order_id IN (SELECT order_id FROM orders WHERE channel = 'web')",
]


@pytest.mark.parametrize("sql", BENIGN)
def test_benign_queries_are_accepted(sql: str) -> None:
    result = validate_sql(sql, POLICY)
    assert result.ok, result.violations
    assert result.normalized_sql and "LIMIT" in result.normalized_sql.upper()


def test_limit_is_injected_and_capped() -> None:
    missing = validate_sql("SELECT order_id FROM orders", POLICY)
    assert missing.limit_applied == 501 and missing.normalized_sql.endswith("LIMIT 501")  # type: ignore[union-attr]
    too_big = validate_sql("SELECT order_id FROM orders LIMIT 100000", POLICY)
    assert too_big.normalized_sql.endswith("LIMIT 501")  # type: ignore[union-attr]
    small = validate_sql("SELECT order_id FROM orders LIMIT 7", POLICY)
    assert small.limit_applied == 7 and small.normalized_sql.endswith("LIMIT 7")  # type: ignore[union-attr]


def test_dataset_schema_qualifier_is_removed() -> None:
    result = validate_sql(f"SELECT COUNT(*) FROM {SCHEMA}.orders", POLICY)
    assert result.tables == ["orders"] and SCHEMA not in (result.normalized_sql or "")


def test_unknown_column_feedback_says_where_the_column_is() -> None:
    result = validate_sql("SELECT o.category FROM orders AS o", POLICY)
    message = result.violations[0].message
    assert "“orders” has no column “category”" in message and "products" in message


def test_unknown_table_suggests_a_close_match() -> None:
    result = validate_sql("SELECT * FROM order", POLICY)
    assert any("Did you mean orders" in v.message for v in result.violations)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT COUNT(*) FROM customers c, orders o",
        "SELECT COUNT(*) FROM customers c CROSS JOIN orders o",
        "SELECT COUNT(*) FROM orders o JOIN order_items oi ON TRUE",
        "SELECT COUNT(*) FROM customers c, orders o, order_items oi",
        "SELECT * FROM orders a, orders b, orders c, order_items d",
        "SELECT COUNT(*) FROM customers c JOIN orders o ON o.customer_id = c.customer_id, order_items oi",
    ],
)
def test_join_without_a_condition_is_rejected(sql: str) -> None:
    result = validate_sql(sql, POLICY)
    assert not result.ok
    assert [v.code for v in result.violations] == ["CARTESIAN_JOIN"]


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT COUNT(*) FROM customers c JOIN orders o ON o.customer_id = c.customer_id",
        "SELECT COUNT(*) FROM customers c JOIN orders o USING (customer_id)",
        "SELECT COUNT(*) FROM customers c, orders o WHERE c.customer_id = o.customer_id",
        # a one-row subquery or CTE is the usual way to get a share of the total
        "SELECT o.status, COUNT(*) * 1.0 / t.n AS share FROM orders o "
        "CROSS JOIN (SELECT COUNT(*) AS n FROM orders) t GROUP BY o.status, t.n",
        "WITH t AS (SELECT COUNT(*) AS n FROM orders) "
        "SELECT o.status, COUNT(*) * 1.0 / t.n FROM orders o CROSS JOIN t GROUP BY o.status, t.n",
    ],
)
def test_joins_with_a_condition_or_one_row_totals_are_accepted(sql: str) -> None:
    assert validate_sql(sql, POLICY).ok


def test_cartesian_message_tells_the_model_how_to_fix_it() -> None:
    result = validate_sql("SELECT COUNT(*) FROM customers c, orders o", POLICY)
    assert "Join on a key" in result.violations[0].message
