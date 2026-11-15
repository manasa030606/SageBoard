"""Backend for the browser tests: the real API, PostgreSQL and agent pipeline, with the language
model replaced by the *oracle* (see ``evals/oracle.py``). Never used in production.

    SAGEBOARD_TEST_* env (see tests/conftest.py)  python -m evals.e2e_server [port]

The oracle answers only the evaluation questions in ``evals/cases.py``; it picks the case by
matching the question text it is sent. Anything else fails the run loudly instead of inventing
an answer.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Any

import uvicorn

from app.agent.llm.client import Completion, LLMMessage, StructuredLLM
from app.main import create_app
from evals.cases import CASES
from evals.oracle import OracleProvider

WEB_ORIGIN = os.environ.get("E2E_WEB_ORIGIN", "http://localhost:3100")


class QuestionRoutedOracle(OracleProvider):
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
        if purpose == "understand_query":
            text = "\n".join(m["content"] for m in messages)
            matches = [c for c in CASES if c.question in text and not c.follow_of]
            if not matches:
                raise RuntimeError("e2e oracle: no evaluation case matches this question")
            self.load(max(matches, key=lambda c: len(c.question)))
        return await super().complete_json(
            purpose=purpose,
            system=system,
            messages=messages,
            schema_name=schema_name,
            json_schema=json_schema,
            temperature=temperature,
        )


def build() -> Any:
    from tests.conftest import make_settings

    settings = make_settings(
        database_url=os.environ["SAGEBOARD_TEST_DATABASE_URL"],
        ingest_database_url=os.environ["SAGEBOARD_TEST_INGEST_DATABASE_URL"],
        executor_database_url=os.environ["SAGEBOARD_TEST_EXECUTOR_DATABASE_URL"],
        upload_dir=Path(tempfile.mkdtemp()),
        demo_dataset_scale="small",
        cors_origins=[WEB_ORIGIN],
        analyses_per_hour=10_000,
    )
    return create_app(settings, agent_llm=StructuredLLM(QuestionRoutedOracle()))


if __name__ == "__main__":
    uvicorn.run(build(), host="127.0.0.1", port=int(sys.argv[1]) if len(sys.argv) > 1 else 8100)
