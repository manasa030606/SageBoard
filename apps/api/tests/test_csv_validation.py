"""CSV validation, type inference and upload storage (no database needed)."""

from __future__ import annotations

import os
import stat
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.core.errors import FileTooLargeError, UnsupportedFileError
from app.ingestion import uploads
from app.ingestion.csv_validation import CsvAnalysis, CsvRejected, Limits, analyze_csv
from app.ingestion.semantics import is_sensitive
from app.ingestion.types import TypeInference, is_missing, parse_value


def write(tmp_path: Path, content: str | bytes, name: str = "data.csv") -> Path:
    path = tmp_path / name
    if isinstance(content, str):
        path.write_text(content, encoding="utf-8")
    else:
        path.write_bytes(content)
    return path


def analyze(tmp_path: Path, content: str | bytes, **limits: int) -> CsvAnalysis:
    return analyze_csv(write(tmp_path, content), Limits(**limits))


def rejected_codes(tmp_path: Path, content: str | bytes, **limits: int) -> set[str]:
    with pytest.raises(CsvRejected) as info:
        analyze(tmp_path, content, **limits)
    return {i.code for i in info.value.issues}


# --------------------------------------------------------------- happy path
def test_infers_types_and_normalises_headers(tmp_path: Path) -> None:
    result = analyze(
        tmp_path,
        "Order ID,Order Date,Amount,Paid,Created At,Region\n"
        '1,2026-01-03,"$1,200.50",yes,2026-01-03T10:00:00Z,West\n'
        "2,2026-01-04,99.10,no,2026-01-04 11:30:00,East\n"
        "3,2026/01/05,,n/a,2026-01-05T09:15:00+02:00,West\n",
    )
    assert result.ok
    assert result.row_count == 3
    types = {c.name: c.inferred_type for c in result.columns}
    assert types == {
        "order_id": "integer",
        "order_date": "date",
        "amount": "numeric",
        "paid": "boolean",
        "created_at": "timestamptz",
        "region": "text",
    }
    by_name = {c.name: c for c in result.columns}
    assert by_name["amount"].missing_count == 1
    assert by_name["paid"].missing_count == 1  # "n/a" is a missing-value token
    assert by_name["order_id"].display_name == "Order ID"


@pytest.mark.parametrize(("delimiter"), [";", "\t", "|"])
def test_detects_delimiter(tmp_path: Path, delimiter: str) -> None:
    rows = ["a", "b", "c"], ["1", "2", "3"], ["4", "5", "6"]
    result = analyze(tmp_path, "\n".join(delimiter.join(r) for r in rows) + "\n")
    assert result.delimiter == delimiter
    assert [c.name for c in result.columns] == ["a", "b", "c"]


def test_utf8_bom_is_accepted(tmp_path: Path) -> None:
    result = analyze(tmp_path, "\ufeffname,value\nx,1\n".encode())
    assert [c.name for c in result.columns] == ["name", "value"]


def test_large_integers_become_bigint(tmp_path: Path) -> None:
    result = analyze(tmp_path, "id\n1\n9000000000\n")
    assert result.columns[0].inferred_type == "bigint"


# ----------------------------------------------------------- missing values
def test_warns_about_empty_and_mostly_missing_columns(tmp_path: Path) -> None:
    result = analyze(tmp_path, "a,b,c\n1,,\n2,,x\n3,,\n")
    codes = {(i.code, i.column) for i in result.issues}
    assert ("EMPTY_COLUMN", "b") in codes
    assert ("HIGH_MISSING", "c") in codes
    assert result.ok  # warnings don't block the upload
    assert {c.name: c.inferred_type for c in result.columns}["b"] == "text"


# ---------------------------------------------------------- header problems
def test_rejects_duplicate_column_names_case_insensitively(tmp_path: Path) -> None:
    assert "DUPLICATE_COLUMN" in rejected_codes(tmp_path, "Amount,amount\n1,2\n")


def test_rejects_names_that_collide_after_normalisation(tmp_path: Path) -> None:
    with pytest.raises(CsvRejected) as info:
        analyze(tmp_path, "Order Date,order-date\n1,2\n")
    issue = next(i for i in info.value.issues if i.code == "DUPLICATE_COLUMN")
    assert "order_date" in issue.message


def test_rejects_blank_column_name(tmp_path: Path) -> None:
    assert "BLANK_COLUMN_NAME" in rejected_codes(tmp_path, "a,,c\n1,2,3\n")


def test_rejects_too_many_columns(tmp_path: Path) -> None:
    header = ",".join(f"c{i}" for i in range(6))
    assert "TOO_MANY_COLUMNS" in rejected_codes(
        tmp_path, f"{header}\n" + "1," * 5 + "1\n", max_columns=5
    )


# ------------------------------------------------------------ file problems
def test_rejects_empty_file(tmp_path: Path) -> None:
    assert "EMPTY_FILE" in rejected_codes(tmp_path, b"")


def test_rejects_header_only(tmp_path: Path) -> None:
    assert "NO_ROWS" in rejected_codes(tmp_path, "a,b\n")


def test_rejects_binary_content(tmp_path: Path) -> None:
    assert "BINARY_FILE" in rejected_codes(tmp_path, b"a,b\n\x00\x01\x02,3\n")


def test_rejects_non_utf8(tmp_path: Path) -> None:
    assert "ENCODING" in rejected_codes(tmp_path, "name\nJosé\n".encode("latin-1"))


def test_rejects_too_many_rows(tmp_path: Path) -> None:
    assert "TOO_MANY_ROWS" in rejected_codes(tmp_path, "a\n" + "1\n" * 6, max_rows=5)


def test_rejects_unbalanced_quotes(tmp_path: Path) -> None:
    content = 'a,b\n1,"never closed\n' + "2,3\n" * 3
    assert rejected_codes(tmp_path, content) & {"MALFORMED_CSV", "CELL_TOO_LARGE"}


def test_rejects_oversized_cell(tmp_path: Path) -> None:
    assert "CELL_TOO_LARGE" in rejected_codes(tmp_path, "a,b\n" + "x" * 20_000 + ",1\n")


def test_a_few_ragged_rows_are_reported_not_fatal(tmp_path: Path) -> None:
    good = "".join(f"{i},{i}\n" for i in range(100))
    result = analyze(tmp_path, "a,b\n" + good + "1,2,3\n")
    assert result.ok
    assert result.row_count == 100
    assert result.rejected_count == 1
    assert result.rejected_rows[0]["line"] == 102
    assert "ROWS_REJECTED" in {i.code for i in result.issues}


def test_many_ragged_rows_reject_the_file(tmp_path: Path) -> None:
    content = "a,b\n" + "1,2\n" * 10 + "1,2,3\n" * 5
    assert "MALFORMED_CSV" in rejected_codes(tmp_path, content)


def test_error_messages_are_actionable(tmp_path: Path) -> None:
    with pytest.raises(CsvRejected) as info:
        analyze(tmp_path, "name\nJosé\n".encode("latin-1"))
    assert "CSV UTF-8" in info.value.issues[0].message


# ----------------------------------------------------------- value parsing
@pytest.mark.parametrize(
    ("column_type", "raw", "expected"),
    [
        ("integer", "42", 42),
        ("integer", "-7", -7),
        ("bigint", "9000000000", 9_000_000_000),
        ("numeric", "$1,200.50", Decimal("1200.50")),
        ("numeric", "€3.5", Decimal("3.5")),
        ("numeric", "-0.25", Decimal("-0.25")),
        ("boolean", "Yes", True),
        ("boolean", "f", False),
        ("date", "2026-02-28", date(2026, 2, 28)),
        ("date", "2026/02/28", date(2026, 2, 28)),
        ("timestamptz", "2026-02-28T10:00:00", datetime(2026, 2, 28, 10, tzinfo=UTC)),
        ("text", "anything", "anything"),
    ],
)
def test_parse_value(column_type: str, raw: str, expected: object) -> None:
    assert parse_value(column_type, raw) == expected  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("column_type", "raw"),
    [
        ("integer", "1.5"),
        ("integer", "3000000000"),  # out of int4 range
        ("numeric", "12abc"),
        ("numeric", "1" * 50),  # beyond numeric precision we accept
        ("boolean", "maybe"),
        ("date", "2026-02-30"),
        ("date", "28/02/2026"),  # ambiguous day/month order is not guessed
        ("timestamptz", "yesterday"),
    ],
)
def test_parse_value_rejects_values_that_do_not_fit(column_type: str, raw: str) -> None:
    with pytest.raises(ValueError, match=r".*"):
        parse_value(column_type, raw)  # type: ignore[arg-type]


@pytest.mark.parametrize("token", ["", "NA", "n/a", "NULL", "None", "nan", "-", "#N/A", "  "])
def test_missing_value_tokens(token: str) -> None:
    assert is_missing(token)


def test_type_inference_falls_back_to_text_on_one_bad_value() -> None:
    inference = TypeInference()
    for value in ["1", "2", "three"]:
        inference.observe(value)
    assert inference.result() == "text"


# --------------------------------------------------------------- sensitivity
@pytest.mark.parametrize(
    "name", ["email", "customer_email", "phone", "first_name", "zip_code", "ip_address"]
)
def test_sensitive_by_name(name: str) -> None:
    assert is_sensitive(name)


def test_sensitive_by_value_shape() -> None:
    assert is_sensitive("contact", ["a@example.com", "b@example.org"])
    assert not is_sensitive("region", ["West", "East"])
    assert not is_sensitive("company", [])


# ------------------------------------------------------------ upload storage
class Chunks:
    def __init__(self, data: bytes, size: int = 7) -> None:
        self._data = data
        self._size = size

    async def read(self, size: int = -1) -> bytes:
        chunk, self._data = self._data[: self._size], self._data[self._size :]
        return chunk


async def test_store_upload_writes_a_private_file(tmp_path: Path) -> None:
    token, path, size = await uploads.store_upload(Chunks(b"a,b\n1,2\n"), tmp_path / "up", 1024)
    assert size == 8
    assert path.read_bytes() == b"a,b\n1,2\n"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE((tmp_path / "up").stat().st_mode) == 0o700
    assert uploads.path_for(tmp_path / "up", token) == path


async def test_store_upload_enforces_size_limit_and_cleans_up(tmp_path: Path) -> None:
    with pytest.raises(FileTooLargeError):
        await uploads.store_upload(Chunks(b"x" * 100), tmp_path, 50)
    assert list(tmp_path.glob("*.upload")) == []


@pytest.mark.parametrize("token", ["../etc/passwd", "a/b", "", "x" * 10, "..", "%2e%2e"])
def test_path_for_rejects_tampered_tokens(tmp_path: Path, token: str) -> None:
    with pytest.raises(ValueError, match=r"invalid upload token|escapes"):
        uploads.path_for(tmp_path, token)


@pytest.mark.parametrize("name", ["report.xlsx", "data.json", "notes.txt", "csv", "evil.csv.exe"])
def test_only_csv_extension_is_accepted(name: str) -> None:
    with pytest.raises(UnsupportedFileError):
        uploads.check_extension(name)
    uploads.check_extension("Sales.CSV")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("../../etc/passwd", "passwd"),
        ("C:\\Users\\me\\sales.csv", "sales.csv"),
        ("a\x00b.csv", "ab.csv"),
        (None, "upload.csv"),
    ],
)
def test_display_names_are_sanitised(raw: str | None, expected: str) -> None:
    assert uploads.safe_display_name(raw) == expected


def test_sweep_removes_only_stale_uploads(tmp_path: Path) -> None:
    old = tmp_path / "old.upload"
    new = tmp_path / "new.upload"
    other = tmp_path / "keep.txt"
    for f in (old, new, other):
        f.write_text("x")
    os.utime(old, (0, 0))
    os.utime(other, (0, 0))
    assert uploads.sweep_stale(tmp_path, ttl_seconds=60) == 1
    assert not old.exists()
    assert new.exists()
    assert other.exists()
