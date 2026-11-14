"""Reports: an immutable snapshot of one finished analysis session.

A report copies what the session produced (question, summary, plan, the SQL that ran)
at the moment it is saved, so later edits to the dataset can't change what it says.
Only sessions that finished (``succeeded`` or ``partial``) can become reports.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.pagination import decode_cursor, encode_cursor
from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.db.models import AnalysisSession, Dataset, QueryExecution, Report, User

REPORTABLE = ("succeeded", "partial")
TITLE_CHARS = 120


class ReportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(
        self, owner: User, *, limit: int, cursor: str | None
    ) -> tuple[Sequence[Report], str | None]:
        stmt = select(Report).where(Report.owner_id == owner.id)
        after = decode_cursor(cursor)
        if after:
            at, last_id = after
            stmt = stmt.where(
                or_(Report.created_at < at, and_(Report.created_at == at, Report.id < last_id))
            )
        stmt = stmt.order_by(Report.created_at.desc(), Report.id.desc()).limit(limit + 1)
        rows = list((await self.session.scalars(stmt)).all())
        next_cursor = None
        if len(rows) > limit:
            rows = rows[:limit]
            next_cursor = encode_cursor(rows[-1].created_at, rows[-1].id)
        return rows, next_cursor

    async def get(self, owner: User, report_id: uuid.UUID) -> Report:
        report = await self.session.scalar(
            select(Report).where(Report.id == report_id, Report.owner_id == owner.id)
        )
        if report is None:
            raise NotFoundError("That report doesn’t exist.")
        return report

    async def create(
        self, owner: User, *, analysis_session_id: uuid.UUID, title: str | None
    ) -> Report:
        run = await self.session.scalar(
            select(AnalysisSession).where(
                AnalysisSession.id == analysis_session_id, AnalysisSession.owner_id == owner.id
            )
        )
        if run is None:
            raise NotFoundError("That analysis doesn’t exist.")
        if run.status not in REPORTABLE:
            raise ConflictError(
                f"Only finished analyses can be saved as reports (this one is {run.status}).",
                code="SESSION_NOT_FINISHED",
            )
        dataset = await self.session.get(Dataset, run.dataset_id)
        queries = (
            await self.session.scalars(
                select(QueryExecution)
                .where(
                    QueryExecution.analysis_session_id == run.id,
                    QueryExecution.exec_status == "ok",
                )
                .order_by(QueryExecution.created_at)
            )
        ).all()
        report = Report(
            owner_id=owner.id,
            analysis_session_id=run.id,
            dataset_id=run.dataset_id,
            title=_clean(title) or _clean(run.question)[:TITLE_CHARS] or "Untitled report",
            summary=run.final_summary or "",
            content=_snapshot(run, dataset, queries),
        )
        self.session.add(report)
        await self.session.commit()
        return report

    async def update(
        self, owner: User, report_id: uuid.UUID, *, title: str | None, summary: str | None
    ) -> Report:
        report = await self.get(owner, report_id)
        if title is not None:
            cleaned = _clean(title)
            if not cleaned:
                raise ValidationFailedError("Enter a title.", code="INVALID_TITLE")
            report.title = cleaned
        if summary is not None and summary != report.summary:
            report.summary = summary
            report.summary_edited_by_user = True
        report.updated_at = datetime.now(UTC)
        await self.session.commit()
        return report

    async def delete(self, owner: User, report_id: uuid.UUID) -> None:
        await self.session.delete(await self.get(owner, report_id))
        await self.session.commit()

    async def export_markdown(self, owner: User, report_id: uuid.UUID) -> tuple[str, str]:
        report = await self.get(owner, report_id)
        return _filename(report.title), render_markdown(report)


def _clean(text: str | None) -> str:
    return " ".join((text or "").split())[:200]


def _snapshot(
    run: AnalysisSession, dataset: Dataset | None, queries: Sequence[QueryExecution]
) -> dict[str, Any]:
    return {
        "question": run.question,
        "status": run.status,
        "dataset": {
            "name": dataset.name if dataset else None,
            "version": run.dataset_version,
        },
        "understanding": run.understanding,
        "plan": run.plan,
        "final_summary": run.final_summary,
        "queries": [
            {"sql": q.executed_sql, "row_count": q.row_count, "truncated": q.truncated}
            for q in queries
            if q.executed_sql
        ],
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }


def _filename(title: str) -> str:
    slug = "".join(c if c.isalnum() else "-" for c in title.lower()).strip("-")
    slug = "-".join(part for part in slug.split("-") if part)[:60]
    return f"{slug or 'report'}.md"


def _fence(sql: str) -> str:
    return "```sql\n" + sql.replace("```", "``\u200b`") + "\n```"


def render_markdown(report: Report) -> str:
    content = report.content
    dataset = content.get("dataset") or {}
    lines = [f"# {report.title}", ""]
    meta = [f"Question: {content.get('question', '')}"]
    if dataset.get("name"):
        meta.append(f"Dataset: {dataset['name']} (version {dataset.get('version')})")
    meta.append(f"Saved: {report.created_at:%Y-%m-%d %H:%M} UTC")
    lines += [f"- {m}" for m in meta] + [""]
    if report.summary:
        lines += ["## Summary", "", report.summary, ""]
    queries = content.get("queries") or []
    if queries:
        lines += ["## Methodology", ""]
        for i, q in enumerate(queries, 1):
            rows = q.get("row_count")
            lines += [
                f"Query {i}" + (f" ({rows} rows)" if rows is not None else ""),
                "",
                _fence(q["sql"]),
                "",
            ]
    if content.get("status") == "partial":
        lines += [
            "## Limitations",
            "",
            "This analysis finished partially; some steps did not complete.",
            "",
        ]
    return "\n".join(lines).rstrip() + "\n"
