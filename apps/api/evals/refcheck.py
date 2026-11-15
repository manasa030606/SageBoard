"""Run every reference query straight through the real executor and compare with the ground truth.

This validates the *dataset* (reference SQL == independent Python truth) before any agent run,
so a failing agent case can never be blamed on a bad expectation.
"""

from __future__ import annotations

from typing import Any

from app.agent.tools.executor import PostgresExecutor
from evals.cases import CASES
from evals.compare import compare
from evals.frames import Frames


async def check_reference(executor: PostgresExecutor, frames: Frames) -> list[dict[str, Any]]:
    out = []
    for case in CASES:
        if case.kind != "answer":
            continue
        assert case.truth is not None
        expected = case.truth(frames)
        steps: dict[str, list[list[Any]]] = {}
        errors = []
        for i, step in enumerate(case.steps, 1):
            outcome = await executor.run(step.sql)
            if outcome.status == "ok":
                steps[f"s{i}"] = [list(r) for r in outcome.rows]
            else:
                errors.append(f"s{i}: {outcome.error_code} {outcome.error_message}")
        result = compare(case.compare, expected, steps)
        out.append(
            {
                "id": case.id,
                "ok": result.exec_match and not errors,
                "errors": errors,
                "detail": result.detail,
                "missing": [repr(m) for m in result.missing[:3]],
            }
        )
    return out
