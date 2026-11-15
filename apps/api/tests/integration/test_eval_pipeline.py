"""A slice of the evaluation run end to end through the real API with the oracle model: one case
per behaviour that matters. The full 62-case run is `python -m evals run --mode oracle`."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from app.core.config import Settings
from evals.cases import BY_ID
from evals.harness import run_eval
from evals.metrics import passed

pytestmark = pytest.mark.integration

SLICE = {
    "S01": "simple count",
    "J01": "join",
    "M01": "multi-step plan",
    "R01": "repairs an unknown column",
    "R04": "repairs a division by zero",
    "I01": "refuses data that does not exist",
    "X01": "a destructive statement never reaches the database",
    "X02": "personal data is not sent to the model",
}


def test_pipeline_slice(pg_settings: Callable[..., Settings], tmp_path: Path) -> None:
    out = tmp_path / "slice.jsonl"
    records = run_eval(
        pg_settings(demo_dataset_scale="small"),
        mode="oracle",
        scale="small",
        out=out,
        ids=list(SLICE),
        log=lambda *_: None,
    )
    by_id = {r["id"]: r for r in records}
    assert set(SLICE) <= set(by_id)  # follow-ups bring their parent along
    for case_id, why in SLICE.items():
        assert passed(by_id[case_id]), (
            f"{case_id} ({why}) did not behave as expected: {by_id[case_id]}"
        )
    # recovery really happened, via the repair node, not by luck
    assert by_id["R01"]["recover_nodes"] >= 1 and by_id["R01"]["first_failure"] == "unknown_column"
    assert BY_ID["X02"].leak_pattern and by_id["X02"]["security"]["leak_in_llm_prompts"] is False
