"""Reports: an immutable snapshot of one finished analysis session.

A report copies what the session produced (question, summary, plan, the SQL that ran)
at the moment it is saved, so later edits to the dataset can't change what it says.
Only sessions that finished (``succeeded`` or ``partial``) can become reports.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.pagination import decode_cursor, encode_cursor
from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.db.models import AnalysisSession, Dataset, QueryExecution, Report, User
from app.db.models.datasets import DatasetTable
from app.reports.fidelity import check_report
from app.reports.markdown import render_markdown
from app.reports.pdf import render_pdf
from app.reports.snapshot import build_snapshot

REPORTABLE = ("succeeded", "partial")
TITLE_CHARS = 120


class ReportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(
        self,
        owner: User,
        *,
        limit: int,
        cursor: str | None,
        analysis_session_id: uuid.UUID | None = None,
    ) -> tuple[Sequence[Report], str | None]:
        stmt = select(Report).where(Report.owner_id == owner.id)
        if analysis_session_id:
            stmt = stmt.where(Report.analysis_session_id == analysis_session_id)
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
        tables = (
            await self.session.scalars(
                select(DatasetTable)
                .where(DatasetTable.dataset_id == run.dataset_id)
                .order_by(DatasetTable.table_name)
            )
        ).all()
        report = Report(
            owner_id=owner.id,
            analysis_session_id=run.id,
            dataset_id=run.dataset_id,
            title=_clean(title) or _clean(run.question)[:TITLE_CHARS] or "Untitled report",
            summary=run.final_summary or "",
            content=build_snapshot(run, dataset, tables, queries),
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

    def fidelity(self, report: Report) -> dict[str, Any]:
        return check_report(report.content, report.summary)

    async def export_markdown(self, owner: User, report_id: uuid.UUID) -> tuple[str, str]:
        report = await self.get(owner, report_id)
        text = render_markdown(
            title=report.title,
            summary=report.summary,
            content=report.content,
            fidelity=self.fidelity(report),
            saved_at=report.created_at,
        )
        return _filename(report.title, "md"), text

    async def export_pdf(self, owner: User, report_id: uuid.UUID) -> tuple[str, bytes]:
        report = await self.get(owner, report_id)
        pdf = await asyncio.to_thread(
            render_pdf,
            title=report.title,
            summary=report.summary,
            content=report.content,
            fidelity=self.fidelity(report),
            saved_at=report.created_at,
            edited=report.summary_edited_by_user,
        )
        return _filename(report.title, "pdf"), pdf


def _clean(text: str | None) -> str:
    return " ".join((text or "").split())[:200]


def _filename(title: str, ext: str) -> str:
    slug = "".join(c if c.isascii() and c.isalnum() else "-" for c in title.lower()).strip(
        "-"
    )  # header-safe
    slug = "-".join(part for part in slug.split("-") if part)[:60]
    return f"{slug or 'report'}.{ext}"
