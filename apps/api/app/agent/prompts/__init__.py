"""Versioned prompt files: ``<node>.v<N>.md``.

The highest version of each prompt is used, and its version string is recorded on
every LLM call so a trace shows exactly which wording produced an output.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import cache
from importlib import resources
from typing import Any

_NAME = re.compile(r"^(?P<name>[a-z_]+)\.v(?P<version>\d+)\.md$")


@dataclass(frozen=True)
class Prompt:
    name: str
    version: str
    system: str


@cache
def load_prompt(name: str) -> Prompt:
    files = resources.files(__package__)
    versions: dict[str, dict[int, str]] = {}
    for entry in files.iterdir():
        if m := _NAME.match(entry.name):
            versions.setdefault(m["name"], {})[int(m["version"])] = entry.read_text("utf-8")
    if name not in versions:
        raise KeyError(f"no prompt named {name}")
    latest = max(versions[name])
    shared = versions["_shared"][max(versions["_shared"])]
    return Prompt(
        name, f"{name}.v{latest}", f"{versions[name][latest].strip()}\n\n{shared.strip()}"
    )


def data_block(name: str, value: Any) -> str:
    """Wrap dataset-derived content so the model treats it as data, not instructions."""
    body = value if isinstance(value, str) else json.dumps(value, default=str, ensure_ascii=False)
    body = body.replace("</data>", "<\\/data>")
    return f'<data name="{name}">\n{body}\n</data>'


def render(*parts: str | tuple[str, Any]) -> str:
    """Join plain instructions and ``(name, value)`` data blocks into one message."""
    out = []
    for part in parts:
        out.append(part if isinstance(part, str) else data_block(*part))
    return "\n\n".join(out)
