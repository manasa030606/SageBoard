"""Phase 8: query history, saved reports and PDF export, end to end on a real database.

The model is scripted (as in the other pipeline tests); catalog, Guard, executor, analysis
tools, persistence and the report/PDF code are real. Figures are checked against the CSV the
test uploaded, not against anything the report code computed.
"""

from __future__ import annotations

import io
import re
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from app.agent.llm.client import StructuredLLM
from app.core.config import Settings
from app.main import create_app
from tests.agent.fakes import ScriptedProvider
from tests.integration.conftest import PASSWORD, sign_up
from tests.integration.test_pipeline_multi_dataset import SALES_CSV, _ask, fill_script

pytestmark = pytest.mark.integration

API = "/api/v1"
QUESTION = "Which region brought in the most revenue?"


def pdf_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text() for page in reader.pages)


def upload_sales(client: TestClient, provider: ScriptedProvider) -> tuple[str, str]:
    uploaded = client.post(
        f"{API}/datasets/uploads",
        files={"file": ("sales.csv", SALES_CSV, "text/csv")},
        data={"name": f"Regional sales {uuid.uuid4().hex[:6]}"},
    )
    assert uploaded.status_code == 201, uploaded.text
    dataset_id = uploaded.json()["dataset"]["id"]
    ready = client.post(f"{API}/datasets/{dataset_id}/finalize", json={"column_types": {}})
    assert ready.status_code == 200, ready.text
    fill_script(provider, ready.json()["tables"][0]["table_name"])
    return dataset_id, uploaded.json()["dataset"]["name"]


@pytest.fixture
def analysed(pg_settings: Callable[..., Settings]) -> Any:
    """A signed-in client with two finished analyses on an uploaded dataset."""
    provider = ScriptedProvider({})
    settings = pg_settings()
    with TestClient(create_app(settings, agent_llm=StructuredLLM(provider))) as client:
        user = sign_up(client)
        dataset_id, dataset_name = upload_sales(client, provider)
        convo = client.post(f"{API}/conversations", json={"dataset_id": dataset_id}).json()
        first = _ask(client, convo["id"], QUESTION)
        second = _ask(client, convo["id"], "Which region had the most orders?")
        assert first["status"] == second["status"] == "succeeded"
        yield {
            "client": client,
            "settings": settings,
            "email": user["user"]["email"],
            "convo": convo,
            "dataset_id": dataset_id,
            "dataset_name": dataset_name,
            "first": first,
            "second": second,
        }


# ------------------------------------------------------------- query history
def test_history_stores_each_analysis_with_what_it_needs_to_be_reopened(analysed: Any) -> None:
    client: TestClient = analysed["client"]
    items = client.get(f"{API}/history/sessions").json()["items"]
    assert [i["question"] for i in items] == ["Which region had the most orders?", QUESTION]

    item = items[1]
    assert item["status"] == "succeeded"
    assert item["dataset_id"] == analysed["dataset_id"]
    assert item["dataset_name"] == analysed["dataset_name"]
    assert item["conversation_id"] == analysed["convo"]["id"]
    assert item["conversation_title"] == QUESTION
    assert item["finding_count"] == 1 and item["query_count"] == 1
    assert "North leads with 440.00" in item["summary"]
    assert item["report_id"] is None
    assert item["created_at"]

    # Reopening: the session carries the plan, SQL, rows, charts and insights.
    stored = client.get(f"{API}/analysis-sessions/{item['id']}").json()
    assert stored["plan"]["steps"][0]["purpose"] == "Total sales by region"
    step = stored["result"]["steps"][0]
    assert "GROUP BY region" in step["sql"] and step["row_count"] == 3
    assert stored["result"]["charts"][0]["chart_type"] == "pie"
    assert stored["result"]["response"]["key_findings"][0]["verification"] == "verified"


def test_history_search_covers_question_answer_and_dataset(analysed: Any) -> None:
    client: TestClient = analysed["client"]

    def find(**params: str) -> list[str]:
        return [
            i["question"]
            for i in client.get(f"{API}/history/sessions", params=params).json()["items"]
        ]

    assert find(q="most revenue") == [QUESTION]
    assert find(q="440.00") == [QUESTION]  # found by what the answer says
    assert find(q=analysed["dataset_name"][:12]) != []  # by dataset name
    assert find(q="no-such-thing") == []
    assert len(find(status="succeeded")) == 2 and find(status="failed") == []
    assert find(since="2999-01-01T00:00:00Z") == []
    assert len(find(dataset_id=analysed["dataset_id"])) == 2
    assert find(dataset_id=str(uuid.uuid4())) == []


def test_history_survives_a_restart_of_the_application(
    analysed: Any, pg_settings: Callable[..., Settings]
) -> None:
    with TestClient(create_app(pg_settings())) as fresh:  # a new process: no in-memory state
        login = fresh.post(
            f"{API}/auth/login", json={"email": analysed["email"], "password": PASSWORD}
        )
        assert login.status_code == 200, login.text
        items = fresh.get(f"{API}/history/sessions").json()["items"]
        assert len(items) == 2
        again = fresh.get(f"{API}/analysis-sessions/{items[1]['id']}").json()
        assert again["result"]["steps"][0]["rows"][0][0] == "North"
        thread = fresh.get(f"{API}/conversations/{analysed['convo']['id']}").json()
        assert [m["role"] for m in thread["messages"]] == ["user", "assistant"] * 2


# ------------------------------------------------------------------- reports
def save_report(client: TestClient, session_id: str) -> dict[str, Any]:
    created = client.post(f"{API}/reports", json={"analysis_session_id": session_id})
    assert created.status_code == 201, created.text
    body: dict[str, Any] = created.json()
    return body


def test_report_snapshot_holds_every_section_from_stored_results(analysed: Any) -> None:
    client: TestClient = analysed["client"]
    report = save_report(client, analysed["first"]["id"])
    content = report["content"]

    assert content["version"] == 2
    assert content["question"] == QUESTION
    assert content["dataset"]["name"] == analysed["dataset_name"]
    assert content["dataset"]["tables"][0]["rows"] == 8
    assert content["executive_summary"] == analysed["first"]["final_summary"]
    assert content["methodology"]["plan_steps"][0]["purpose"] == "Total sales by region"
    assert "GROUP BY region" in content["steps"][0]["sql"]
    assert content["steps"][0]["rows"][0][0] == "North"
    assert content["findings"][0]["headline"].startswith("North leads with 440.00")
    assert content["charts"][0]["chart_type"] == "pie" and len(content["charts"][0]["data"]) == 3
    assert report["fidelity"] == {"status": "verified", "checked": 2, "issues": []}

    # History now links the analysis to its report, and the report list can be filtered by it.
    history = client.get(f"{API}/history/sessions", params={"q": "most revenue"}).json()["items"]
    assert history[0]["report_id"] == report["id"]
    by_session = client.get(
        f"{API}/reports", params={"analysis_session_id": analysed["first"]["id"]}
    )
    assert [r["id"] for r in by_session.json()["items"]] == [report["id"]]
    other = client.get(f"{API}/reports", params={"analysis_session_id": analysed["second"]["id"]})
    assert other.json()["items"] == []


def test_pdf_contains_all_ten_sections_and_the_stored_figures(analysed: Any) -> None:
    client: TestClient = analysed["client"]
    report = save_report(client, analysed["first"]["id"])
    response = client.get(f"{API}/reports/{report['id']}/export.pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].endswith('.pdf"')
    assert response.headers["cache-control"] == "no-store"
    assert response.content.startswith(b"%PDF-")

    text = pdf_text(response.content)
    for heading in (
        QUESTION,  # title and question
        "Dataset",
        "Executive summary",
        "Analysis methodology",
        "SQL queries",
        "Key findings",
        "Visualizations",
        "Business recommendations",
        "Limitations",
    ):
        assert heading in text, heading
    assert analysed["dataset_name"] in text
    assert "GROUP BY region" in text  # the SQL that actually ran
    assert "Share of sales by region" in text  # chart title
    assert "North" in text and "440" in text  # numbers from the stored rows
    assert "Numbers not found" not in text
    assert "matched against the stored query results" in text

    # Independent check: every number printed in the summary section is a real number
    # from the uploaded data (440 / 400 / 260, their sum 1,100, or a count).
    truth = {440.0, 400.0, 260.0, 1100.0, 3.0, 8.0}
    summary_block = text.split("Executive summary")[1].split("Analysis methodology")[0]
    for raw in re.findall(r"\d[\d,]*\.?\d*", summary_block):
        assert float(raw.replace(",", "")) in truth, raw


def test_an_edited_summary_with_an_invented_number_is_flagged_in_api_and_pdf(analysed: Any) -> None:
    client: TestClient = analysed["client"]
    report = save_report(client, analysed["first"]["id"])
    edited = client.patch(
        f"{API}/reports/{report['id']}", json={"summary": "Revenue grew 97% year over year."}
    ).json()
    assert edited["summary_edited_by_user"] is True
    assert edited["fidelity"]["status"] == "flagged"
    assert edited["fidelity"]["issues"] == [{"where": "Executive summary", "numbers": ["97%"]}]

    text = pdf_text(client.get(f"{API}/reports/{report['id']}/export.pdf").content)
    assert "Numbers not found in the stored results" in text and "97%" in text
    assert "edited after the analysis ran" in text
    markdown = client.get(f"{API}/reports/{report['id']}/export.md").text
    assert "Numbers not found in the stored results" in markdown

    # Restoring a truthful summary clears the flag.
    fixed = client.patch(f"{API}/reports/{report['id']}", json={"summary": "North led with 440."})
    assert fixed.json()["fidelity"]["status"] == "verified"


def test_markup_and_odd_characters_in_a_report_cannot_break_the_pdf(analysed: Any) -> None:
    client: TestClient = analysed["client"]
    report = save_report(client, analysed["first"]["id"])
    nasty = (
        "<b>bold</b> <font size=900>big</font> <img src='http://x/y.png'/> "
        + chr(0x202E)
        + " "
        + chr(0)
        + " ✓ 日本語 & <"
    )
    ok = client.patch(
        f"{API}/reports/{report['id']}", json={"title": nasty[:100], "summary": nasty}
    )
    assert ok.status_code == 200
    response = client.get(f"{API}/reports/{report['id']}/export.pdf")
    assert response.status_code == 200 and response.content.startswith(b"%PDF-")
    text = pdf_text(response.content)
    assert "<b>bold</b>" in text  # shown literally, not interpreted as markup
    assert "<font size=900>" in text


def test_reports_and_history_are_private_to_their_owner(
    analysed: Any, pg_settings: Callable[..., Settings]
) -> None:
    owner: TestClient = analysed["client"]
    report = save_report(owner, analysed["first"]["id"])

    with TestClient(create_app(pg_settings())) as intruder:
        sign_up(intruder)
        assert intruder.get(f"{API}/history/sessions").json()["items"] == []
        assert intruder.get(f"{API}/reports").json()["items"] == []
        for path in ("", "/export.pdf", "/export.md"):
            assert intruder.get(f"{API}/reports/{report['id']}{path}").status_code == 404
        assert (
            intruder.patch(f"{API}/reports/{report['id']}", json={"title": "mine"}).status_code
            == 404
        )
        assert intruder.delete(f"{API}/reports/{report['id']}").status_code == 404
        assert (
            intruder.post(
                f"{API}/reports", json={"analysis_session_id": analysed["first"]["id"]}
            ).status_code
            == 404
        )
        assert (
            intruder.get(
                f"{API}/reports", params={"analysis_session_id": analysed["first"]["id"]}
            ).json()["items"]
            == []
        )
        assert intruder.get(f"{API}/analysis-sessions/{analysed['first']['id']}").status_code == 404

    # And nothing changed for the owner.
    assert owner.get(f"{API}/reports/{report['id']}").json()["title"] == report["title"]
