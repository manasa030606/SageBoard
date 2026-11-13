"""Safe storage of uploaded files.

- The client's filename is never used on disk; files get a random token name.
- The upload directory is created with 0700 permissions.
- Size is enforced while streaming, so an oversized upload is never fully written.
- Only the token is stored in the database; paths are rebuilt from it and checked
  to stay inside the upload directory.
"""

from __future__ import annotations

import contextlib
import os
import re
import secrets
import time
from pathlib import Path
from typing import Protocol

from app.core.errors import FileTooLargeError, UnsupportedFileError

CHUNK = 1024 * 1024
ALLOWED_EXTENSIONS = (".csv",)
_TOKEN = re.compile(r"^[A-Za-z0-9_-]{32,64}$")


class AsyncReadable(Protocol):
    async def read(self, size: int = -1) -> bytes: ...


def safe_display_name(filename: str | None) -> str:
    """Keep only the base name, strip control characters, cap the length (display only)."""
    base = os.path.basename((filename or "upload.csv").replace("\\", "/"))
    base = re.sub(r"[\x00-\x1f\x7f]", "", base).strip() or "upload.csv"
    return base[:200]


def check_extension(filename: str) -> None:
    lower = filename.lower()
    if lower.endswith((".xlsx", ".xls")):
        raise UnsupportedFileError(
            "Excel files aren’t supported yet. Save the sheet as “CSV UTF-8” and upload that."
        )
    if not lower.endswith(ALLOWED_EXTENSIONS):
        raise UnsupportedFileError("Only .csv files can be uploaded.")


def upload_dir(base: Path) -> Path:
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(base, 0o700)
    return base


def path_for(base: Path, token: str) -> Path:
    if not _TOKEN.fullmatch(token):
        raise ValueError("invalid upload token")
    path = (base / f"{token}.upload").resolve()
    if path.parent != base.resolve():
        raise ValueError("upload path escapes the upload directory")
    return path


async def store_upload(source: AsyncReadable, base: Path, max_bytes: int) -> tuple[str, Path, int]:
    """Stream ``source`` to a new private file. Returns (token, path, size)."""
    directory = upload_dir(base)
    token = secrets.token_urlsafe(32)
    path = path_for(directory, token)
    size = 0
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as out:
            while chunk := await source.read(CHUNK):
                size += len(chunk)
                if size > max_bytes:
                    raise FileTooLargeError(
                        f"The file is larger than {max_bytes // (1024 * 1024)} MB.",
                        details={"max_bytes": max_bytes},
                    )
                out.write(chunk)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return token, path, size


def discard(base: Path, token: str | None) -> None:
    if token:
        with contextlib.suppress(ValueError):  # malformed token: nothing of ours to delete
            path_for(base, token).unlink(missing_ok=True)


def sweep_stale(base: Path, ttl_seconds: int) -> int:
    """Delete abandoned uploads older than the TTL. Returns how many were removed."""
    if not base.exists():
        return 0
    removed = 0
    cutoff = time.time() - ttl_seconds
    for item in base.glob("*.upload"):
        if item.is_file() and not item.is_symlink() and item.stat().st_mtime < cutoff:
            item.unlink(missing_ok=True)
            removed += 1
    return removed
