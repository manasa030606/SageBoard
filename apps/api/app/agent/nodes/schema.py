"""Schema Retrieval: a bounded tool-calling loop.

The model sees only table names at first and asks for details with tools, one action
per turn, until it calls ``finish``. Tool calls are capped (``max_schema_tool_calls``);
tool errors go back to the model as observations so it can correct itself. The final
``SchemaContext`` is built by code from the real catalog, so it can only contain
tables and columns that exist.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agent.llm.client import LLMMessage
from app.agent.nodes.common import understanding_payload
from app.agent.prompts import data_block, load_prompt, render
from app.agent.runtime import NodeContext
from app.agent.state import AgentState, SchemaContext
from app.agent.tools.schema import SchemaToolError, SchemaTools

MAX_TABLES_PER_CALL = 4
SMALL_DATASET_TABLES = 8


class SchemaAction(BaseModel):
    action: Literal["get_table_schema", "get_join_paths", "get_column_values", "finish"]
    tables: list[str] = Field(default_factory=list, max_length=8)
    table: str | None = None
    column: str | None = None
    selected_tables: list[str] = Field(default_factory=list, max_length=12)
    rationale: str = Field(default="", max_length=500)


def build_context(
    tools: SchemaTools, tables: list[str], rationale: str, calls: int
) -> SchemaContext:
    valid = [t for t in dict.fromkeys(tables) if t in tools.table_names]
    columns = [tools.column_context(t, c.name) for t in valid for c in tools.table(t).columns]
    joins = tools.get_join_paths(valid) if len(valid) > 1 else []
    return SchemaContext(
        tables=valid, columns=columns, join_paths=joins, rationale=rationale, tool_calls=calls
    )


async def _run_tool(ctx: NodeContext, action: SchemaAction) -> Any:
    tools = ctx.deps.schema
    if action.action == "get_table_schema":
        names = action.tables or ([action.table] if action.table else [])
        if not names:
            raise SchemaToolError("get_table_schema needs `tables`")
        names = names[:MAX_TABLES_PER_CALL]
        return await ctx.tool(
            "get_table_schema",
            {"tables": names},
            lambda: [tools.get_table_schema(n) for n in names],
        )
    if action.action == "get_join_paths":
        return await ctx.tool(
            "get_join_paths", {"tables": action.tables}, lambda: tools.get_join_paths(action.tables)
        )
    if not action.table or not action.column:
        raise SchemaToolError("get_column_values needs `table` and `column`")
    table, column = action.table, action.column
    return await ctx.tool(
        "get_column_values",
        {"table": table, "column": column},
        lambda: tools.get_column_values(table, column),
    )


async def retrieve_schema(state: AgentState, ctx: NodeContext) -> dict[str, Any]:
    prompt = load_prompt("retrieve_schema")
    tools = ctx.deps.schema
    messages: list[LLMMessage] = [
        {
            "role": "user",
            "content": render(
                ("question", state["question"]),
                ("understanding", understanding_payload(state)),
                (
                    "tables",
                    [
                        {k: t[k] for k in ("table", "description", "row_count")}
                        for t in state["table_catalog"]
                    ],
                ),
                f"You may make at most {ctx.budget.max_schema_tool_calls} tool calls.",
            ),
        }
    ]
    inspected: list[str] = []
    calls = 0
    finished: SchemaAction | None = None
    while calls <= ctx.budget.max_schema_tool_calls:
        action = await ctx.llm(prompt, messages, SchemaAction)
        if action.action == "finish":
            finished = action
            break
        if calls == ctx.budget.max_schema_tool_calls:
            break  # cap reached: proceed with what was collected
        calls += 1
        try:
            observation: Any = await _run_tool(ctx, action)
            if action.action == "get_table_schema":
                inspected += [t["table"] for t in observation]
        except SchemaToolError as exc:
            observation = {"error": str(exc)}
        messages += [
            {"role": "assistant", "content": action.model_dump_json(exclude_defaults=True)},
            {
                "role": "user",
                "content": data_block(
                    "observation", json.dumps(observation, default=str, ensure_ascii=False)
                ),
            },
        ]

    selected = (finished.selected_tables if finished else []) or inspected
    rationale = (
        finished.rationale if finished else "Tool-call limit reached; using inspected tables."
    )
    context = build_context(tools, selected, rationale, calls)
    if not context.tables:
        if len(tools.table_names) <= SMALL_DATASET_TABLES:
            context = build_context(
                tools,
                tools.table_names,
                "No tables selected; using the whole (small) dataset.",
                calls,
            )
            ctx.degraded_reason = "model selected no valid tables"
        else:
            ctx.summary = {"tables": [], "tool_calls": calls}
            return {
                "schema_context": context,
                "termination_reason": "out_of_scope",
                "errors": ["retrieve_schema: no relevant tables found"],
            }
    ignored = sorted(set(selected) - set(context.tables))
    ctx.summary = {
        "tables": context.tables,
        "join_paths": context.join_paths,
        "tool_calls": calls,
        "finished": finished is not None,
        **({"ignored_unknown_tables": ignored} if ignored else {}),
    }
    return {"schema_context": context}


def retrieve_schema_fallback(state: AgentState, exc: Exception, ctx: NodeContext) -> dict[str, Any]:
    """The tool loop failed: a small dataset is used whole; otherwise the run stops."""
    tools = ctx.deps.schema
    if len(tools.table_names) > SMALL_DATASET_TABLES:
        return {"termination_reason": "error"}
    reason = f"Schema retrieval failed ({type(exc).__name__}); using the whole dataset."
    return {"schema_context": build_context(tools, tools.table_names, reason, 0)}
