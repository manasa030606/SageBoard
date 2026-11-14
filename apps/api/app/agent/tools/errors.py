"""Deterministic error classification for the Error Recovery agent.

Classifying in code (not with the model) keeps recovery predictable: each category
comes with a fixed hint and decides whether a retry is worth spending budget on.
"""

from __future__ import annotations

from app.agent.state import ErrorCategory, ErrorDiagnosis, SQLAttempt

GUARD_CODE_CATEGORY: dict[str, ErrorCategory] = {
    "SYNTAX_ERROR": "syntax_error",
    "UNKNOWN_TABLE": "unknown_table",
    "UNKNOWN_COLUMN": "unknown_column",
    "AMBIGUOUS_COLUMN": "ambiguous_column",
    "INVALID_REFERENCE": "unknown_column",
}

SQLSTATE_CATEGORY: dict[str, ErrorCategory] = {
    "42601": "syntax_error",
    "42P01": "unknown_table",
    "42703": "unknown_column",
    "42803": "grouping_error",
    "42804": "type_mismatch",
    "42883": "undefined_function",
    "22P02": "type_mismatch",
    "22007": "type_mismatch",
    "22008": "type_mismatch",
    "22003": "type_mismatch",
    "22012": "division_by_zero",
    "42702": "ambiguous_column",
    "57014": "timeout",
    "42501": "permission_denied",
    "25006": "guard_rejected",
}

HINTS: dict[ErrorCategory, str] = {
    "guard_rejected": "Write a single read-only SELECT over this dataset's tables only.",
    "syntax_error": "Fix the PostgreSQL syntax; keep the query as simple as possible.",
    "unknown_table": "Use only the tables listed in the schema context.",
    "unknown_column": "Use only columns listed for each table; join the table that holds the column.",
    "grouping_error": "Every non-aggregated column in SELECT must appear in GROUP BY.",
    "type_mismatch": "Cast explicitly and compare dates/timestamps with date literals (DATE '2025-01-01').",
    "undefined_function": "Use standard PostgreSQL functions and cast arguments to the expected types.",
    "division_by_zero": "Protect divisions with NULLIF(denominator, 0).",
    "ambiguous_column": "Qualify every column with its table alias.",
    "timeout": "The query was too slow: aggregate before joining, add filters, avoid cross joins.",
    "permission_denied": "Only this dataset's tables can be read.",
    "empty_result": "Check filter values against the sampled column values and the data's date range.",
    "fan_out": "The join multiplied rows: aggregate before joining or join on unique keys.",
    "repeated_query": "This query was already tried. Write a materially different query.",
    "other": "Rewrite the query more simply.",
}

NOT_RECOVERABLE: frozenset[ErrorCategory] = frozenset({"permission_denied"})


def classify_attempt(attempt: SQLAttempt, *, repeated: bool = False) -> ErrorDiagnosis:
    """Classify why ``attempt`` failed (Guard rejection or database error)."""
    if repeated:
        category: ErrorCategory = "repeated_query"
        summary = "The corrected query is identical to one that already failed."
    elif attempt.guard_status == "rejected":
        first = attempt.guard_violations[0] if attempt.guard_violations else None
        category = (
            GUARD_CODE_CATEGORY.get(first.code, "guard_rejected") if first else "guard_rejected"
        )
        summary = "; ".join(f"{v.code}: {v.message}" for v in attempt.guard_violations) or (
            "Rejected by the SQL Guard."
        )
    elif attempt.exec_status == "timeout":
        category, summary = "timeout", attempt.exec_error or "The query timed out."
    else:
        category = SQLSTATE_CATEGORY.get(attempt.error_code or "", "other")
        summary = f"{attempt.error_code or 'error'}: {attempt.exec_error or 'database error'}"
    return ErrorDiagnosis(
        category=category,
        recoverable=category not in NOT_RECOVERABLE,
        summary=summary[:500],
        hint=HINTS[category],
    )


def result_problem(category: ErrorCategory, summary: str) -> ErrorDiagnosis:
    """A diagnosis for a query that ran but returned an unusable result."""
    return ErrorDiagnosis(
        category=category, recoverable=True, summary=summary, hint=HINTS[category]
    )
