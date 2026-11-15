"""Render a report snapshot as a PDF (reportlab, no browser, no network).

All text comes from stored results or model output, so every string is XML-escaped
before it reaches a ``Paragraph`` (which parses a small markup language) and characters
the bundled font can't draw are replaced rather than printed as boxes.
"""

from __future__ import annotations

import io
import os
import unicodedata
from datetime import datetime
from typing import Any
from xml.sax.saxutils import escape

import reportlab
from reportlab.graphics.charts.barcharts import HorizontalBarChart, VerticalBarChart
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Flowable,
    KeepTogether,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.reports.fidelity import FLAGGED, VERIFIED

_FONT_DIR = os.path.join(os.path.dirname(reportlab.__file__), "fonts")
SANS, SANS_BOLD, SANS_ITALIC, MONO = "Vera", "Vera-Bold", "Vera-Italic", "Courier"
INK = colors.HexColor("#1F2933")
MUTED = colors.HexColor("#5F6C7B")
RULE = colors.HexColor("#D5DBE3")
ACCENT = colors.HexColor("#2F6FDE")
PALETTE = [
    colors.HexColor(c) for c in ("#2F6FDE", "#E0813A", "#2E9E83", "#8B5CC4", "#C94F6D", "#7A8793")
]
PAGE_W, PAGE_H = A4
MARGIN = 20 * mm
CONTENT_W = PAGE_W - 2 * MARGIN
MAX_SQL_LINE = 92
MAX_CELL = 28
MAX_CHART_POINTS = 12
ANGLE_AFTER = 6  # more categories than this: angle the x labels
LEGEND_BOTTOM = 8
FLAG_GLYPHS = {"’": "'", "\u2018": "'", "“": '"', "”": '"', "–": "-", "—": "-"}

_fonts_ready = False


def _register_fonts() -> None:
    global _fonts_ready  # noqa: PLW0603 - one-time registration
    if _fonts_ready:
        return
    for name, file in ((SANS, "Vera.ttf"), (SANS_BOLD, "VeraBd.ttf"), (SANS_ITALIC, "VeraIt.ttf")):
        pdfmetrics.registerFont(TTFont(name, os.path.join(_FONT_DIR, file)))
    pdfmetrics.registerFontFamily(
        SANS, normal=SANS, bold=SANS_BOLD, italic=SANS_ITALIC, boldItalic=SANS_BOLD
    )
    _fonts_ready = True


def _printable(text: object) -> str:
    """Text the font can draw: normalise, then drop control characters and glyphs Vera lacks."""
    raw = unicodedata.normalize("NFC", "" if text is None else str(text))
    font = pdfmetrics.getFont(SANS)
    out = []
    for original in raw:
        ch = FLAG_GLYPHS.get(original, original)
        if ch in "\n\t" or (ch.isprintable() and ord(ch) in font.face.charToGlyph):
            out.append(ch)
        elif unicodedata.category(ch)[0] != "C":
            out.append("?")
    return "".join(out)


def _p(text: object) -> str:
    return escape(_printable(text))


def _styles() -> dict[str, ParagraphStyle]:
    base = ParagraphStyle(
        "base", fontName=SANS, fontSize=9.5, leading=14, textColor=INK, alignment=TA_LEFT
    )
    return {
        "body": base,
        "small": ParagraphStyle("small", parent=base, fontSize=8, leading=11, textColor=MUTED),
        "title": ParagraphStyle(
            "title", parent=base, fontName=SANS_BOLD, fontSize=22, leading=27, spaceAfter=4
        ),
        "h1": ParagraphStyle(
            "h1",
            keepWithNext=1,
            parent=base,
            fontName=SANS_BOLD,
            fontSize=13,
            leading=17,
            spaceBefore=16,
            spaceAfter=6,
        ),
        "h2": ParagraphStyle(
            "h2",
            keepWithNext=1,
            parent=base,
            fontName=SANS_BOLD,
            fontSize=10,
            leading=14,
            spaceBefore=8,
            spaceAfter=2,
        ),
        "meta": ParagraphStyle("meta", parent=base, fontSize=9, leading=13, textColor=MUTED),
        "cell": ParagraphStyle("cell", parent=base, fontSize=8, leading=10),
        "cellh": ParagraphStyle("cellh", parent=base, fontName=SANS_BOLD, fontSize=8, leading=10),
        "bullet": ParagraphStyle(
            "bullet", parent=base, leftIndent=12, bulletIndent=2, spaceAfter=3
        ),
        "notice": ParagraphStyle("notice", parent=base, fontSize=8.5, leading=12),
    }


class _Rule(Flowable):  # type: ignore[misc]  # reportlab ships no type information
    def __init__(self, width: float = CONTENT_W, color: colors.Color = RULE) -> None:
        super().__init__()
        self.width, self.height, self.color = width, 1, color
        self.keepWithNext = 1  # a section heading never ends a page on its own

    def draw(self) -> None:
        self.canv.setStrokeColor(self.color)
        self.canv.setLineWidth(0.6)
        self.canv.line(0, 0, self.width, 0)


def _num(value: Any, fmt: str = "number") -> str:
    if isinstance(value, bool) or value is None:
        return "" if value is None else str(value)
    if isinstance(value, int | float):
        if fmt == "percent":
            return f"{value * 100:,.1f}%" if abs(value) <= 1 else f"{value:,.1f}%"
        if fmt == "currency":
            return f"{value:,.2f}"
        if isinstance(value, float) and not value.is_integer():
            return f"{value:,.2f}"
        return f"{int(value):,}"
    return str(value)


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _table(columns: list[str], rows: list[list[Any]], st: dict[str, ParagraphStyle]) -> Table:
    shown = columns[:8]
    data: list[list[Paragraph]] = [[Paragraph(_p(c), st["cellh"]) for c in shown]]
    for row in rows:
        data.append(
            [
                Paragraph(
                    _p(_num(v) if isinstance(v, int | float) else str(v)[:MAX_CELL]), st["cell"]
                )
                for v in row[: len(shown)]
            ]
        )
    table = Table(data, colWidths=[CONTENT_W / max(len(shown), 1)] * len(shown), repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEF2F7")),
                ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table


# ------------------------------------------------------------------- charts
def _chart(chart: dict[str, Any], st: dict[str, ParagraphStyle]) -> list[Flowable]:
    columns: list[str] = chart.get("columns") or []
    rows: list[list[Any]] = chart.get("data") or []
    title = [Paragraph(_p(chart.get("title") or "Chart"), st["h2"])]
    if chart.get("subtitle"):
        title.append(Paragraph(_p(chart["subtitle"]), st["small"]))
    kind, x, ys = chart.get("chart_type"), chart.get("x"), chart.get("y") or []
    fmt = chart.get("value_format") or "number"
    if not rows or not columns:
        return [
            KeepTogether([*title, Paragraph("No data was stored for this chart.", st["small"])])
        ]
    idx = {name: i for i, name in enumerate(columns)}

    if kind == "kpi":
        value = rows[0][idx[ys[0]]] if ys and ys[0] in idx else rows[0][0]
        drawing = Drawing(CONTENT_W, 40)
        drawing.add(
            String(
                0,
                12,
                _printable(_num(value, fmt)),
                fontName=SANS_BOLD,
                fontSize=26,
                fillColor=ACCENT,
            )
        )
        return [KeepTogether([*title, drawing])]

    drawable = kind in {
        "bar",
        "grouped_bar",
        "horizontal_bar",
        "histogram",
        "line",
        "area",
        "pie",
        "donut",
    }
    ycols = [y for y in ys if y in idx]
    if drawable and x in idx and ycols:
        series = [[_numeric(r[idx[y]]) for r in rows[: MAX_CHART_POINTS * 3]] for y in ycols]
        labels = [str(r[idx[x]])[:14] for r in rows[: MAX_CHART_POINTS * 3]]
        if all(v is not None for s in series for v in s):
            drawing = _draw(
                kind or "bar",
                labels,
                [[float(v) for v in s if v is not None] for s in series],
                ycols,
            )
            note = []
            if len(rows) > len(labels) or chart.get("rows_total", 0) > len(rows):
                note = [Paragraph("Chart shows the first rows returned.", st["small"])]
            return [KeepTogether([*title, drawing, *note])]
    # scatter, tables and anything that can't be drawn faithfully: show the data itself
    return [KeepTogether([*title, _table(columns, rows[:TABLE_FALLBACK_ROWS], st)])]


TABLE_FALLBACK_ROWS = 10


def _draw(  # noqa: PLR0915 - one branch per chart type
    kind: str, labels: list[str], series: list[list[float]], names: list[str]
) -> Drawing:
    height = 190
    drawing = Drawing(CONTENT_W, height)
    if kind in {"pie", "donut"}:
        pie = Pie()
        pie.x, pie.y, pie.width, pie.height = 40, 20, 150, 150
        pie.data = [abs(v) for v in series[0]]
        pie.labels = None
        for i in range(len(pie.data)):
            pie.slices[i].fillColor = PALETTE[i % len(PALETTE)]
            pie.slices[i].strokeColor = colors.white
        if kind == "donut":
            pie.innerRadiusFraction = 0.55
        drawing.add(pie)
        total = sum(pie.data) or 1
        for i, (label, v) in enumerate(zip(labels, pie.data, strict=False)):
            y = height - 24 - i * 13
            if y < LEGEND_BOTTOM:
                break
            drawing.add(
                Rect(208, y - 1, 7, 7, fillColor=PALETTE[i % len(PALETTE)], strokeColor=None)
            )
            drawing.add(
                String(
                    220,
                    y,
                    _printable(f"{label}  {v / total * 100:.1f}%"),
                    fontName=SANS,
                    fontSize=8,
                    fillColor=INK,
                )
            )
        return drawing
    if kind in {"line", "area"}:
        plot = LinePlot()
        plot.x, plot.y, plot.width, plot.height = 40, 30, CONTENT_W - 60, height - 50
        plot.data = [[(i, v) for i, v in enumerate(s)] for s in series]
        for i in range(len(series)):
            plot.lines[i].strokeColor = PALETTE[i % len(PALETTE)]
            plot.lines[i].strokeWidth = 1.6
        plot.xValueAxis.valueMin, plot.xValueAxis.valueMax = 0, max(len(labels) - 1, 1)
        plot.xValueAxis.valueSteps = list(range(len(labels)))
        plot.xValueAxis.labelTextFormat = lambda v: (
            _printable(labels[int(v)]) if 0 <= int(v) < len(labels) else ""
        )
        plot.xValueAxis.labels.fontName = plot.yValueAxis.labels.fontName = SANS
        plot.xValueAxis.labels.fontSize = plot.yValueAxis.labels.fontSize = 7
        plot.xValueAxis.labels.angle = 30 if len(labels) > ANGLE_AFTER else 0
        plot.xValueAxis.labels.boxAnchor = "ne" if len(labels) > ANGLE_AFTER else "n"
        drawing.add(plot)
    else:
        horizontal = kind == "horizontal_bar"
        chart = HorizontalBarChart() if horizontal else VerticalBarChart()
        chart.x, chart.y, chart.width, chart.height = (
            50 if horizontal else 40,
            30,
            CONTENT_W - 70,
            height - 50,
        )
        # reportlab draws the first category at the bottom; ranked bars read top-down
        chart.data = [s[::-1] for s in series] if horizontal else series
        chart.categoryAxis.categoryNames = [
            _printable(label) for label in (labels[::-1] if horizontal else labels)
        ]
        chart.categoryAxis.labels.fontName = chart.valueAxis.labels.fontName = SANS
        chart.categoryAxis.labels.fontSize = chart.valueAxis.labels.fontSize = 7
        if not horizontal and len(labels) > ANGLE_AFTER:
            chart.categoryAxis.labels.angle = 30
            chart.categoryAxis.labels.boxAnchor = "ne"
        chart.bars.strokeColor = None
        for i in range(len(series)):
            chart.bars[i].fillColor = PALETTE[i % len(PALETTE)]
        lo = min(min(s) for s in series)
        chart.valueAxis.valueMin = min(0.0, lo)
        drawing.add(chart)
    if len(series) > 1:
        for i, name in enumerate(names):
            x0 = 46 + i * 110
            drawing.add(
                Rect(x0, height - 11, 7, 7, fillColor=PALETTE[i % len(PALETTE)], strokeColor=None)
            )
            drawing.add(
                String(
                    x0 + 11,
                    height - 10,
                    _printable(name[:18]),
                    fontName=SANS,
                    fontSize=8,
                    fillColor=INK,
                )
            )
    return drawing


# ------------------------------------------------------------------ document
def _bullets(items: list[str], st: dict[str, ParagraphStyle]) -> list[Flowable]:
    return [Paragraph(_p(i), st["bullet"], bulletText="•") for i in items]


def _wrap_sql(sql: str) -> str:
    lines: list[str] = []
    for source in _printable(sql).replace("\t", "    ").splitlines():
        line = source
        while len(line) > MAX_SQL_LINE:
            cut = line.rfind(" ", 0, MAX_SQL_LINE)
            cut = cut if cut > MAX_SQL_LINE // 2 else MAX_SQL_LINE
            lines.append(line[:cut])
            line = "    " + line[cut:].lstrip()
        lines.append(line)
    return "\n".join(lines)


def _section(title: str, st: dict[str, ParagraphStyle]) -> list[Flowable]:
    gap = Spacer(1, 6)
    gap.keepWithNext = 1
    return [Paragraph(_p(title), st["h1"]), _Rule(), gap]


def render_pdf(  # noqa: PLR0912, PLR0915 - one linear document
    *,
    title: str,
    summary: str,
    content: dict[str, Any],
    fidelity: dict[str, Any],
    saved_at: datetime,
    edited: bool,
) -> bytes:
    _register_fonts()
    st = _styles()
    dataset = content.get("dataset") or {}
    method = content.get("methodology") or {}
    story: list[Flowable] = [
        Paragraph(_p(title), st["title"]),
        Paragraph(
            _p(f"Saved {saved_at:%Y-%m-%d %H:%M} UTC · Sageboard analysis report"), st["meta"]
        ),
        Spacer(1, 4),
        _Rule(color=ACCENT),
    ]

    story += [*_section("Question", st), Paragraph(_p(content.get("question")), st["body"])]
    if method.get("restated_question") and method["restated_question"] != content.get("question"):
        story.append(Paragraph(_p(f"Interpreted as: {method['restated_question']}"), st["small"]))

    story += _section("Dataset", st)
    rows = [
        ["Name", dataset.get("name") or "Unknown"],
        ["Version", f"{dataset.get('version', '?')}"],
    ]
    if dataset.get("description"):
        rows.append(["Description", dataset["description"]])
    tables = dataset.get("tables") or []
    if tables:
        rows.append(["Tables", ", ".join(f"{t['name']} ({_num(t['rows'])} rows)" for t in tables)])
    info = Table(
        [[Paragraph(_p(k), st["cellh"]), Paragraph(_p(v), st["cell"])] for k, v in rows],
        colWidths=[28 * mm, CONTENT_W - 28 * mm],
    )
    info.setStyle(
        TableStyle(
            [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE)]
        )
    )
    story.append(info)

    story += _section("Executive summary", st)
    if edited:
        story.append(Paragraph("This summary was edited after the analysis ran.", st["small"]))
    story.append(Paragraph(_p(summary or "No summary was produced."), st["body"]))
    if fidelity.get("status") == FLAGGED:
        lines = [f"{i['where']}: {', '.join(i['numbers'])}" for i in fidelity["issues"]]
        notice = Table(
            [
                [
                    Paragraph(
                        "<b>Numbers not found in the stored results</b><br/>"
                        + "<br/>".join(_p(x) for x in lines),
                        st["notice"],
                    )
                ]
            ],
            colWidths=[CONTENT_W],
        )
        notice.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFF4E5")),
                    ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#E0813A")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story += [Spacer(1, 6), notice]

    story += _section("Analysis methodology", st)
    desc = []
    for label, key in (("Intent", "intent"), ("Time range", "time_range")):
        if method.get(key):
            desc.append(f"{label}: {method[key]}")
    for label, key in (
        ("Metrics", "metrics"),
        ("Dimensions", "dimensions"),
        ("Filters", "filters"),
    ):
        if method.get(key):
            desc.append(f"{label}: {', '.join(method[key])}")
    story += _bullets(desc, st)
    if method.get("plan_steps"):
        story.append(Paragraph("Plan", st["h2"]))
        story += _bullets([f"{s['step_id']}: {s['purpose']}" for s in method["plan_steps"]], st)
    if method.get("analysis_tasks"):
        story.append(Paragraph("Calculations performed on the results", st["h2"]))
        story += _bullets(method["analysis_tasks"], st)
    ver = method.get("verification")
    if ver:
        story.append(
            Paragraph(
                _p(
                    f"Verification: {ver.get('verified_insights', 0)} insights verified, {ver.get('rejected_insights', 0)} rejected; metrics check: {ver.get('metrics_check')}; time period check: {ver.get('time_period_check')}."
                ),
                st["small"],
            )
        )

    story += _section("SQL queries", st)
    steps = [s for s in content.get("steps") or [] if s.get("sql")]
    if steps:
        for s in steps:
            head = f"{s['step_id']}" + (f": {s['purpose']}" if s.get("purpose") else "")
            count = f" · {_num(s['row_count'])} rows" if s.get("row_count") is not None else ""
            story.append(
                Paragraph(
                    _p(head + count + (" (truncated)" if s.get("truncated") else "")), st["h2"]
                )
            )
            story.append(
                Preformatted(
                    _wrap_sql(s["sql"]),
                    ParagraphStyle(
                        "sql",
                        fontName=MONO,
                        fontSize=7.5,
                        leading=9.5,
                        backColor=colors.HexColor("#F4F6F9"),
                        borderPadding=5,
                        textColor=INK,
                    ),
                )
            )
            story.append(Spacer(1, 5))
    else:
        for i, q in enumerate(content.get("queries") or [], 1):
            story.append(Paragraph(f"Query {i}", st["h2"]))
            story.append(
                Preformatted(
                    _wrap_sql(q["sql"]),
                    ParagraphStyle(
                        "sql",
                        fontName=MONO,
                        fontSize=7.5,
                        leading=9.5,
                        backColor=colors.HexColor("#F4F6F9"),
                        borderPadding=5,
                    ),
                )
            )
        if not content.get("queries"):
            story.append(Paragraph("No SQL was stored for this analysis.", st["small"]))

    story += _section("Key findings", st)
    findings = content.get("findings") or []
    if findings:
        for f in findings:
            story.append(
                KeepTogether(
                    [
                        Paragraph(_p(f["headline"]), st["h2"]),
                        Paragraph(_p(f["detail"]), st["body"]),
                        Paragraph(
                            _p(
                                f"{f['category']} · confidence {f['confidence']} · {f['verification']}"
                            ),
                            st["small"],
                        ),
                    ]
                )
            )
    else:
        story.append(Paragraph("No verified findings were stored for this analysis.", st["small"]))
    facts = [f for f in content.get("facts") or [] if isinstance(f.get("value"), int | float)]
    if facts:
        story.append(Paragraph("Computed values", st["h2"]))
        story.append(
            _table(
                ["Value", "What it is", "Step"],
                [
                    [
                        _num(f["value"]) + (f" {f['unit']}" if f.get("unit") else ""),
                        f["description"],
                        f["step_id"],
                    ]
                    for f in facts[:12]
                ],
                st,
            )
        )

    story += _section("Visualizations", st)
    charts = content.get("charts") or []
    if charts:
        for c in charts:
            story += _chart(c, st)
            story.append(Spacer(1, 8))
    else:
        story.append(Paragraph("This analysis produced no charts.", st["small"]))

    story += _section("Business recommendations", st)
    recs = content.get("recommendations") or []
    if recs:
        for r in recs:
            story.append(
                KeepTogether(
                    [Paragraph(_p(r["headline"]), st["h2"]), Paragraph(_p(r["detail"]), st["body"])]
                )
            )
    else:
        story.append(
            Paragraph(
                "The analysis did not support any recommendation strongly enough to state one.",
                st["small"],
            )
        )

    story += _section("Limitations", st)
    story += _bullets(content.get("limitations") or ["No specific limitations were recorded."], st)
    fid = {
        VERIFIED: "Every number in this report was matched against the stored query results.",
        FLAGGED: "Some numbers could not be matched against the stored results (see the notice under the summary).",
    }.get(fidelity.get("status", ""), "Numeric verification was not available for this report.")
    story += [Spacer(1, 6), Paragraph(_p(fid), st["small"])]

    buffer = io.BytesIO()

    def footer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setFont(SANS, 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(MARGIN, 12 * mm, _printable(title)[:80])
        canvas.drawRightString(PAGE_W - MARGIN, 12 * mm, f"Page {doc.page}")
        canvas.restoreState()

    SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=22 * mm,
        title=_printable(title)[:200],
        author="Sageboard",
        subject="Analysis report",
    ).build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
