from __future__ import annotations

from app.core.logging import _redact_secrets


def test_secret_like_keys_are_redacted() -> None:
    event = {
        "event": "x",
        "api_key": "sk-123",
        "password": "p",
        "Authorization": "Bearer t",
        "session_token": "t",
        "dataset_id": "keep-me",
    }
    out = _redact_secrets(None, "info", event)
    assert out["api_key"] == out["password"] == out["Authorization"] == "«redacted»"
    assert out["session_token"] == "«redacted»"
    assert out["dataset_id"] == "keep-me"
