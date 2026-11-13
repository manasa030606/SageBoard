"""CSV validation and analysis (pure, file-based, no database access).

Reads an uploaded CSV once, streaming, and produces:
- the header (original and normalised names) and detected delimiter
- a suggested type per column, missing-value counts and small samples
- a list of *issues*: errors block the upload, warnings are shown for review
- the data rows that would be rejected (wrong number of fields)

Every issue has a stable ``code`` so the UI and tests can rely on it.
"""

from __future__ import annotations

import csv
import io
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from app.ingestion.identifiers import normalize_identifier
from app.ingestion.types import ColumnType, TypeInference, is_missing

Severity = Literal["error", "warning"]

MAX_CELL_CHARS = 10_000
SNIFF_BYTES = 64 * 1024
MAX_REJECTED_SAMPLES = 50
MAX_REJECTED_RATIO = 0.05
HIGH_MISSING_RATIO = 0.5
SAMPLE_VALUES = 5


@dataclass(frozen=True)
class Limits:
    max_rows: int = 1_000_000
    max_columns: int = 200


@dataclass
class Issue:
    severity: Severity
    code: str
    message: str
    column: str | None = None
    line: int | None = None

    def as_dict(self) -> dict[str, object]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class ColumnAnalysis:
    name: str
    display_name: str
    inferred_type: ColumnType
    missing_count: int
    sample_values: list[str]

    def as_dict(self) -> dict[str, object]:
        return dict(self.__dict__)


@dataclass
class CsvAnalysis:
    delimiter: str
    columns: list[ColumnAnalysis]
    row_count: int
    rejected_rows: list[dict[str, object]]
    rejected_count: int
    issues: list[Issue] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def ok(self) -> bool:
        return not self.errors


class CsvRejected(Exception):
    """The file cannot be used at all (malformed, empty, wrong encoding…)."""

    def __init__(self, issues: list[Issue]) -> None:
        super().__init__("; ".join(i.message for i in issues))
        self.issues = issues


def _detect_delimiter(sample: str) -> str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        first_line = sample.splitlines()[0] if sample else ""
        counts = {d: first_line.count(d) for d in ",;\t|"}
        best = max(counts, key=lambda d: counts[d])
        return best if counts[best] > 0 else ","


def _read_text_sample(path: Path) -> str:
    raw = path.read_bytes()[:SNIFF_BYTES]
    if not raw.strip():
        raise CsvRejected([Issue("error", "EMPTY_FILE", "The file is empty.")])
    if b"\x00" in raw:
        raise CsvRejected(
            [
                Issue(
                    "error",
                    "BINARY_FILE",
                    "The file contains binary data (NUL bytes). Export it as a plain-text CSV.",
                )
            ]
        )
    try:
        # Cut at the last newline so a multi-byte character split at the boundary is not a false error.
        cut = raw.rfind(b"\n")
        (raw[: cut + 1] if cut > 0 else raw).decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CsvRejected(
            [
                Issue(
                    "error",
                    "ENCODING",
                    f"The file is not valid UTF-8 (byte {exc.start}). Save it as “CSV UTF-8” and upload again.",
                )
            ]
        ) from exc
    return raw.decode("utf-8-sig", errors="ignore")


def _validate_header(header: list[str], limits: Limits) -> tuple[list[str], list[Issue]]:
    issues: list[Issue] = []
    cleaned = [h.strip() for h in header]
    if not cleaned or all(not h for h in cleaned):
        return [], [Issue("error", "NO_HEADER", "The first row must contain column names.")]
    if len(cleaned) > limits.max_columns:
        issues.append(
            Issue(
                "error",
                "TOO_MANY_COLUMNS",
                f"The file has {len(cleaned)} columns; the limit is {limits.max_columns}.",
            )
        )
    for index, name in enumerate(cleaned):
        if not name:
            issues.append(
                Issue("error", "BLANK_COLUMN_NAME", f"Column {index + 1} has no name.", line=1)
            )

    exact = Counter(h.lower() for h in cleaned if h)
    for name, count in exact.items():
        if count > 1:
            issues.append(
                Issue(
                    "error",
                    "DUPLICATE_COLUMN",
                    f"The column name “{name}” appears {count} times.",
                    column=name,
                )
            )

    normalized = [
        normalize_identifier(h) if h else f"column_{i + 1}" for i, h in enumerate(cleaned)
    ]
    by_norm: dict[str, list[str]] = {}
    for original, norm in zip(cleaned, normalized, strict=True):
        by_norm.setdefault(norm, []).append(original)
    for norm, originals in by_norm.items():
        if len(originals) > 1 and len({o.lower() for o in originals}) > 1:
            issues.append(
                Issue(
                    "error",
                    "DUPLICATE_COLUMN",
                    f"The columns {', '.join(f'“{o}”' for o in originals)} would all become “{norm}”. Rename one of them.",
                    column=norm,
                )
            )
    return normalized, issues


def analyze_csv(  # noqa: PLR0912, PLR0915 - one streaming pass keeps memory flat
    path: Path, limits: Limits | None = None
) -> CsvAnalysis:
    limits = limits or Limits()
    sample = _read_text_sample(path)
    delimiter = _detect_delimiter(sample)
    with open_csv(path, delimiter) as (_handle, reader):
        try:
            header = next(reader)
        except StopIteration:
            raise CsvRejected([Issue("error", "EMPTY_FILE", "The file is empty.")]) from None
        except csv.Error as exc:
            raise CsvRejected(
                [Issue("error", "MALFORMED_CSV", f"The header row can’t be read: {exc}.", line=1)]
            ) from exc

        names, issues = _validate_header(header, limits)
        if any(i.severity == "error" for i in issues):
            raise CsvRejected(issues)
        width = len(names)
        inference = [TypeInference() for _ in names]
        missing = [0] * width
        samples: list[list[str]] = [[] for _ in names]
        rejected: list[dict[str, object]] = []
        rejected_count = 0
        rows = 0

        while True:
            try:
                record = next(reader)
            except StopIteration:
                break
            except UnicodeDecodeError as exc:
                raise CsvRejected(
                    [
                        Issue(
                            "error",
                            "ENCODING",
                            f"Invalid UTF-8 near line {reader.line_num + 1}. Save the file as “CSV UTF-8”.",
                        )
                    ]
                ) from exc
            except csv.Error as exc:
                message = str(exc)
                code = "CELL_TOO_LARGE" if "field larger" in message else "MALFORMED_CSV"
                text = (
                    f"A value near line {reader.line_num} is longer than {MAX_CELL_CHARS:,} characters."
                    if code == "CELL_TOO_LARGE"
                    else f"Line {reader.line_num} can’t be parsed ({message}). Check for unbalanced quotes."
                )
                raise CsvRejected([Issue("error", code, text, line=reader.line_num)]) from exc

            if not record or all(not cell.strip() for cell in record):
                continue  # blank line
            rows += 1
            if rows > limits.max_rows:
                raise CsvRejected(
                    [
                        Issue(
                            "error",
                            "TOO_MANY_ROWS",
                            f"The file has more than {limits.max_rows:,} rows.",
                        )
                    ]
                )
            if len(record) != width:
                rejected_count += 1
                if len(rejected) < MAX_REJECTED_SAMPLES:
                    rejected.append(
                        {
                            "line": reader.line_num,
                            "reason": f"expected {width} values, found {len(record)}",
                        }
                    )
                continue
            for i, cell in enumerate(record):
                if is_missing(cell):
                    missing[i] += 1
                    continue
                inference[i].observe(cell)
                if len(samples[i]) < SAMPLE_VALUES and cell.strip() not in samples[i]:
                    samples[i].append(cell.strip()[:80])

    if rows == 0:
        raise CsvRejected([Issue("error", "NO_ROWS", "The file has a header but no data rows.")])
    if rejected_count / rows > MAX_REJECTED_RATIO:
        first = rejected[0]
        raise CsvRejected(
            [
                Issue(
                    "error",
                    "MALFORMED_CSV",
                    f"{rejected_count:,} of {rows:,} rows have the wrong number of values "
                    f"(first at line {first['line']}: {first['reason']}). Check the delimiter and quoting.",
                    line=int(str(first["line"])),
                )
            ]
        )

    valid_rows = rows - rejected_count
    columns: list[ColumnAnalysis] = []
    for i, name in enumerate(names):
        col_type = inference[i].result()
        columns.append(ColumnAnalysis(name, header[i].strip(), col_type, missing[i], samples[i]))
        ratio = missing[i] / valid_rows if valid_rows else 1
        if missing[i] == valid_rows:
            issues.append(
                Issue(
                    "warning",
                    "EMPTY_COLUMN",
                    f"“{header[i].strip()}” has no values. It will be loaded as text.",
                    column=name,
                )
            )
        elif ratio > HIGH_MISSING_RATIO:
            issues.append(
                Issue(
                    "warning",
                    "HIGH_MISSING",
                    f"“{header[i].strip()}” is missing in {ratio:.0%} of rows.",
                    column=name,
                )
            )
    if rejected_count:
        issues.append(
            Issue(
                "warning",
                "ROWS_REJECTED",
                f"{rejected_count:,} rows have the wrong number of values and will be skipped.",
            )
        )
    # row_count = rows that will be loaded; rejected rows are counted separately.
    return CsvAnalysis(delimiter, columns, valid_rows, rejected, rejected_count, issues)


@contextmanager
def open_csv(path: Path, delimiter: str) -> Iterator[tuple[io.TextIOWrapper, Any]]:
    """The one CSV reader configuration, shared by analysis and loading so they agree.

    ``strict=True`` makes an unclosed quote an error instead of silently swallowing the
    rest of the file into one cell.
    """
    csv.field_size_limit(MAX_CELL_CHARS)
    with path.open("r", encoding="utf-8-sig", newline="", errors="strict") as handle:
        yield handle, csv.reader(handle, delimiter=delimiter, strict=True)
