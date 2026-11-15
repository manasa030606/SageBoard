"""The *oracle* model: a scripted stand-in that replays each case's reference SQL.

What it is: the same test double the integration suite uses (``tests/agent/fakes.py``), driven
by the evaluation case instead of a hand-written script. Everything except the model is real:
Guard, read-only executor on PostgreSQL, analysis engine, grounding/verification, persistence,
API. What it is not: a measurement of any language model. Numbers produced with it describe
the *pipeline* (does correct SQL survive the system intact, do recovery and safety layers work,
how long does the machinery take) and must never be quoted as model accuracy.
"""

from __future__ import annotations

import re
from typing import Any

from app.agent.llm.client import Completion, LLMMessage
from app.agent.tools.charts import NUMERIC_PG_TYPES
from evals.cases import Case
from tests.agent.fakes import ScriptedProvider, data_from

TABLES = ("customers", "products", "orders", "order_items", "payments")


def _tables_in(sql: str) -> list[str]:
    return [t for t in TABLES if re.search(rf"\b{t}\b", sql)]


def _fmt(value: Any) -> str:
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{value:,.2f}"
    return str(value)


class OracleProvider(ScriptedProvider):
    name = "oracle"
    model = "oracle-reference-sql"

    def __init__(self) -> None:
        super().__init__({})
        self.case: Case | None = None
        self._gen = 0
        self._sql_for_step: dict[str, str] = {}

    def load(self, case: Case) -> None:
        self.case = case
        self._gen = 0
        self._sql_for_step = {}
        self.calls.clear()
        self.unexpected.clear()

    # ------------------------------------------------------------------ replies
    async def complete_json(
        self,
        *,
        purpose: str,
        system: str,
        messages: list[LLMMessage],
        schema_name: str,
        json_schema: dict[str, Any],
        temperature: float,
    ) -> Completion:
        from tests.agent.fakes import Call

        self.calls.append(Call(purpose, system, list(messages)))
        assert self.case is not None, "OracleProvider.load(case) was not called"
        reply = getattr(self, f"_{purpose}")(self.case, messages)
        return Completion(reply, self.model, tokens_in=0, tokens_out=0)

    def _understand_query(self, c: Case, m: list[LLMMessage]) -> dict[str, Any]:
        base: dict[str, Any] = {
            "restated_question": c.resolved or c.question,
            "intent": "aggregate",
            "metrics": [],
            "dimensions": [],
            "filters": [],
            "assumptions": [],
        }
        if c.kind == "refuse":
            return {**base, "status": "out_of_scope", "out_of_scope_reason": c.refusal_reason}
        return {**base, "status": "answerable"}

    def _sqls(self, c: Case) -> list[str]:
        return [s.sql for s in c.steps] if c.steps else [c.attack_sql or ""]

    def _retrieve_schema(self, c: Case, m: list[LLMMessage]) -> dict[str, Any]:
        tables = sorted({t for sql in self._sqls(c) for t in _tables_in(sql)}) or ["orders"]
        return {
            "action": "finish",
            "selected_tables": tables,
            "rationale": "tables used by the query",
        }

    def _plan_analysis(self, c: Case, m: list[LLMMessage]) -> dict[str, Any]:
        steps = c.steps or ()
        if not steps:
            return {
                "steps": [
                    {
                        "step_id": "s1",
                        "purpose": "Answer the question",
                        "expected_output": "the answer",
                        "depends_on": [],
                    }
                ],
                "analysis_tasks": [],
                "final_answer_shape": "A direct answer.",
            }
        return {
            "steps": [
                {
                    "step_id": f"s{i}",
                    "purpose": s.purpose,
                    "expected_output": "result rows",
                    "depends_on": [],
                }
                for i, s in enumerate(steps, 1)
            ],
            "analysis_tasks": [s.purpose.lower() for s in steps],
            "final_answer_shape": "A direct answer with the supporting numbers.",
        }

    def _generate_sql(self, c: Case, m: list[LLMMessage]) -> dict[str, Any]:
        idx = self._gen
        self._gen += 1
        step_id = data_from(m, "current_step").get("step_id", f"s{idx + 1}")
        sqls = self._sqls(c)
        good = sqls[min(idx, len(sqls) - 1)]
        self._sql_for_step[step_id] = good
        if c.faulty and idx == len(sqls) - 1:  # the wrong first attempt for the answer step
            return {"sql": c.faulty[0], "explanation": "first attempt"}
        return {"sql": good, "explanation": "reference query"}

    def _recover_error(self, c: Case, m: list[LLMMessage]) -> dict[str, Any]:
        step_id = data_from(m, "current_step").get("step_id", "s1")
        return {
            "diagnosis": "Corrected according to the error and schema.",
            "sql": self._sql_for_step.get(step_id, self._sqls(c)[-1]),
            "change_summary": "reference query",
        }

    def _analyze_results(self, c: Case, m: list[LLMMessage]) -> dict[str, Any]:
        calls = []
        for step in data_from(m, "results"):
            if step["row_count"] < 2:
                continue  # single rows become lookup facts automatically
            cols = step["columns"]
            nums = [x["name"] for x in cols if x["type"] in NUMERIC_PG_TYPES]
            labels = [x["name"] for x in cols if x["type"] not in NUMERIC_PG_TYPES]
            if nums and labels:
                calls.append(
                    {
                        "tool": "top_n",
                        "step_id": step["step_id"],
                        "label_column": labels[0],
                        "value_column": nums[-1],
                        "n": 3,
                        "description": f"Top values of {nums[-1]}",
                    }
                )
            elif nums:
                calls.append(
                    {
                        "tool": "total",
                        "step_id": step["step_id"],
                        "column": nums[-1],
                        "description": f"Total of {nums[-1]}",
                    }
                )
        return {"calls": calls[:6]}

    def _generate_visualization(self, c: Case, m: list[LLMMessage]) -> dict[str, Any]:
        return {"charts": []}

    def _generate_insights(self, c: Case, m: list[LLMMessage]) -> dict[str, Any]:
        facts = data_from(m, "facts")
        usable = [f for f in facts if f["kind"] in ("lookup", "total", "top_n")]
        if usable:
            f = usable[0]
            v = f["value"]
            if isinstance(v, list):
                head = f"{v[0]['label']} leads with {_fmt(v[0]['value'])}"
            else:
                head = f"{f['description']}: {_fmt(v)}"
            ev = [{"kind": "fact", "fact_id": f["fact_id"]}]
        else:
            step = data_from(m, "results")[0]
            col = step["columns"][0]["name"]
            cell = step["rows"][0]["values"][0]
            head = f"{col}: {_fmt(cell)}"
            ev = [{"kind": "cell", "step_id": step["step_id"], "row_index": 0, "column": col}]
        return {
            "insights": [
                {
                    "headline": head[:160],
                    "detail": "Taken directly from the query result.",
                    "category": "finding",
                    "evidence": ev,
                    "confidence": "high",
                }
            ]
        }

    def _verify_insights(self, c: Case, m: list[LLMMessage]) -> dict[str, Any]:
        return {
            "metrics_match": True,
            "time_period_match": True,
            "insights": [
                {"insight_id": i["insight_id"], "supported": True} for i in data_from(m, "insights")
            ],
        }

    def _compose_response(self, c: Case, m: list[LLMMessage]) -> dict[str, Any]:
        verified = data_from(m, "verified_insights")
        return {
            "summary": (verified[0]["headline"] + ".")
            if verified
            else "The query ran; see the result table."
        }
