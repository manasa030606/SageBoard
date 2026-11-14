"""Check the configured model with ONE tiny request (uses 1 of your daily quota).

    uv run python scripts/check_llm.py            # test LLM_PROVIDER / LLM_MODEL
    uv run python scripts/check_llm.py --list     # Google only: models this key can call

Tells you whether the key works, whether the model exists, and whether it has
free-tier quota (Google answers "limit: 0" for models your free tier can't use).
The key is read from apps/api/.env and never printed.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import httpx
from pydantic import BaseModel

from app.agent.llm.client import LLMError
from app.agent.llm.factory import NOT_CONFIGURED_MESSAGE, build_llm
from app.core.config import LLMProvider, get_settings

GOOGLE_MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"


class Ping(BaseModel):
    ok: bool
    word: str


async def check() -> int:
    settings = get_settings()
    llm = build_llm(settings)
    if llm is None:
        print(NOT_CONFIGURED_MESSAGE, file=sys.stderr)
        return 2
    provider, model = llm.label
    print(
        f"Provider: {provider} · model: {model} · client pacing: {settings.llm_requests_per_minute or 'off'} req/min"
    )
    try:
        result = await llm.structured(
            purpose="check",
            prompt_version="check.v1",
            system="Reply only with JSON matching the schema.",
            messages=[{"role": "user", "content": 'Set ok to true and word to "ready".'}],
            schema=Ping,
        )
    except LLMError as exc:
        print(f"FAILED [{exc.code}] {exc}")
        return 1
    print(
        f"OK — structured reply {result.value.model_dump()} · tokens {result.tokens_in}+{result.tokens_out}"
    )
    return 0


async def list_google_models() -> int:
    settings = get_settings()
    key = settings.google_api_key
    if settings.llm_provider is not LLMProvider.GOOGLE or key is None:
        print("--list needs LLM_PROVIDER=google and GOOGLE_API_KEY.", file=sys.stderr)
        return 2
    async with httpx.AsyncClient(timeout=30) as http:
        response = await http.get(
            GOOGLE_MODELS_URL,
            headers={"x-goog-api-key": key.get_secret_value()},
            params={"pageSize": 200},
        )
    if response.status_code != httpx.codes.OK:
        print(f"FAILED HTTP {response.status_code}")
        return 1
    for m in response.json().get("models", []):
        if "generateContent" in m.get("supportedGenerationMethods", []):
            print(m["name"].removeprefix("models/"))
    print(
        "\nListed models can be called with your key; free-tier quota per model is shown in AI Studio."
    )
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="list models your Google key can call (no generation request is made)",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(list_google_models() if args.list else check()))
