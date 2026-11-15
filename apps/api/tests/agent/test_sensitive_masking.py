"""Sensitive column values must not reach the model (SECURITY_DESIGN §6)."""

from __future__ import annotations

from app.agent.nodes.common import HIDDEN, sensitive_columns, step_payload
from app.agent.state import AgentState, ColumnContext, SchemaContext, StepResult


def _result() -> StepResult:
    return StepResult(
        step_id="s1",
        status="succeeded",
        columns=[("first_name", "text"), ("email", "text"), ("orders", "bigint")],
        row_count=2,
        preview_rows=[["Ada", "ada@example.com", 3], ["Bob", "bob@example.com", 5]],
    )


def _state() -> AgentState:
    cols = [
        ColumnContext(table="customers", column="first_name", data_type="text", is_sensitive=True),
        ColumnContext(table="customers", column="email", data_type="text", is_sensitive=True),
        ColumnContext(table="customers", column="segment", data_type="text"),
    ]
    return {
        "schema_context": SchemaContext(
            tables=["customers"], columns=cols, join_paths=[], rationale=""
        )
    }


def test_sensitive_names_are_collected_case_insensitively() -> None:
    assert sensitive_columns(_state()) == {"first_name", "email"}
    assert sensitive_columns(AgentState()) == frozenset()


def test_hidden_values_never_appear_in_payload() -> None:
    payload = step_payload(_result(), hidden=frozenset({"first_name", "email"}))
    blob = str(payload)
    assert "Ada" not in blob and "ada@example.com" not in blob and "bob@example.com" not in blob
    assert payload["rows"][0]["values"] == [HIDDEN, HIDDEN, 3]
    assert payload["hidden_columns"] == ["first_name", "email"]
    assert payload["columns"][0] == {"name": "first_name", "type": "text"}  # name stays visible


def test_non_sensitive_results_are_untouched() -> None:
    payload = step_payload(_result())
    assert payload["rows"][0]["values"] == ["Ada", "ada@example.com", 3]
    assert "hidden_columns" not in payload


def test_stored_result_is_not_modified() -> None:
    result = _result()
    step_payload(result, hidden=frozenset({"email"}))
    assert result.preview_rows[0][1] == "ada@example.com"
