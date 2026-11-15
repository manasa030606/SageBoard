"""Write the evaluation dataset, with expected results, to JSON so it can be read and reviewed
without running any code. Expected values come from the independent ground-truth functions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evals.cases import CASES
from evals.frames import Frames


def export_dataset(scale: str, out: Path) -> int:
    frames = Frames(scale)
    cases: list[dict[str, Any]] = []
    for c in CASES:
        item: dict[str, Any] = {
            "id": c.id,
            "category": c.category,
            "kind": c.kind,
            "question": c.question,
            "tags": list(c.tags),
        }
        if c.follow_of:
            item |= {"follow_up_of": c.follow_of, "resolved_question": c.resolved}
        if c.kind == "answer" and c.truth is not None:
            item |= {
                "comparison": c.compare,
                "reference_sql": [{"purpose": s.purpose, "sql": s.sql} for s in c.steps],
                "expected_rows": [list(r) for r in c.truth(frames)],
            }
            if c.faulty:
                item |= {
                    "injected_first_attempts": list(c.faulty),
                    "expected_first_failure": c.faulty_kind,
                }
        elif c.kind == "refuse":
            item |= {"expected": "refusal, no findings", "reason": c.refusal_reason}
        else:
            item |= {
                "attack_sql": c.attack_sql,
                "expected": "blocked or harmless; database unchanged",
                "must_not_appear": c.leak_pattern,
            }
        cases.append(item)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "dataset": "retail_v1",
                "scale": scale,
                "seed": 20261113,
                "case_count": len(cases),
                "note": "Expected rows are computed in plain Python from the seeded generator, not by SQL.",
                "cases": cases,
            },
            indent=2,
            default=str,
        )
        + "\n"
    )
    return len(cases)
