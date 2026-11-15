"""Render result files into docs/eval/EVALUATION_SUMMARY.md. Pure formatting: no numbers are typed here."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evals.cases import CASES, CATEGORIES
from evals.metrics import compute, failure_rows


def pct(m: dict[str, Any]) -> str:
    return (
        "n/a (no cases)" if m["value"] is None else f"{m['value'] * 100:.1f}% ({m['n']}/{m['d']})"
    )


def ms(d: dict[str, Any]) -> str:
    if not d.get("count"):
        return "n/a"
    return f"p50 {d['p50']:.0f} · p95 {d['p95']:.0f} · mean {d['mean']:.0f} · max {d['max']:.0f} (n={d['count']})"


def load(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def section(title: str, mode: str, scale: str, recs: list[dict[str, Any]]) -> list[str]:
    m = compute(recs)
    banner = (
        "> **Oracle mode.** The language model is replaced by a script that replays each case's reference SQL. "
        "Guard, executor, analysis engine, verification, grounding, API and persistence are real. These numbers measure "
        "the *pipeline*. They say nothing about how well any language model writes SQL."
        if mode == "oracle"
        else f"> **Live mode.** Real model: {recs[0].get('model', 'see result file') if recs else ''}. Accuracy figures below are model-and-pipeline together."
    )
    L = [
        f"## {title}",
        "",
        banner,
        "",
        f"Scale `{scale}` · cases run **{m['cases_run']}** of {len(CASES)} · not run: {m['cases_not_run']} · "
        f"overall correct outcome **{pct(m['overall_pass'])}**",
        "",
        "| # | Metric | Result | Definition (denominator) |",
        "|---|---|---|---|",
        f"| 1 | SQL execution accuracy | {pct(m['m1_sql_execution_accuracy'])} | answerable cases whose result matches the independently computed truth |",
        f"| 1b | SQL execution success | {pct(m['m1b_sql_execution_success'])} | answerable cases where at least one step ran without error |",
        f"| 2 | Numerical result accuracy | {pct(m['m2_numerical_accuracy'])} | expected numeric cells found in the agent's result (integers exact, others 0.01 % / 0.01) |",
        f"| 3 | Schema grounding (first attempt) | {pct(m['m3_schema_grounding_first_try'])} | generated steps whose first SQL used only real tables and columns |",
        f"| 3b | Cases with every step schema-valid first try | {pct(m['m3b_cases_with_all_steps_schema_valid'])} | answerable cases |",
        f"| 4 | Task completion (answerable) | {pct(m['m4_task_completion_answerable'])} | answerable cases ending with an answer and ≥ 1 successful query |",
        f"| 4b | Correct refusal (invalid schema) | {pct(m['m4b_correct_refusal'])} | questions about data that does not exist |",
        f"| 4c | Fabricated answers on invalid schema | {pct(m['m4c_fabricated_answer_on_invalid_schema'])} | same cases (lower is better) |",
        f"| 5 | Error recovery success | {pct(m['m5_error_recovery_steps'])} | steps that needed more than one attempt and ended successful |",
        f"| 5b | First failure classified as expected | {pct(m['m5b_failure_classified_as_expected'])} | error-recovery cases |",
        f"| 6 | Insight faithfulness | {pct(m['m6_insight_faithfulness_verified_reports'])} | saved reports whose every number re-verifies against stored results |",
        f"| 6b | Tampered summary detected | {pct(m['m6b_tampered_summary_detected'])} | reports edited to include an invented number |",
        f"| 7 | Query execution latency (ms) | {ms(m['m7_query_execution_ms'])} | successful SQL executions (database time) |",
        f"| 8 | End-to-end response latency (ms) | {ms(m['m8_end_to_end_ms'])} | question submitted → run finished, all cases |",
        f"| 9 | SQL safety (pipeline security cases) | {pct(m['m9_pipeline_security_cases_safe'])} | security cases: nothing unsafe executed, database unchanged, no sensitive values sent to the model |",
        f"| 9b | Sensitive values sent to the model | {pct(m['m9b_sensitive_values_in_llm_prompts'])} | security cases that ask for personal data (lower is better) |",
        f"| 9c | Sensitive values in the stored result shown to the owner | {pct(m['m9c_sensitive_values_in_stored_results'])} | same cases; a product decision, see FAILURE_ANALYSIS.md |",
        f"| – | Follow-up: earlier turn passed to the agent | {pct(m['follow_up_context_passed'])} | follow-up cases (oracle only) |",
        f"| – | Model calls per case / tokens | {m['llm_calls_per_case']:.1f} / {m['tokens_total']} | all cases |"
        if m["llm_calls_per_case"] is not None
        else "",
        "",
        "**By category**",
        "",
        "| Category | Correct outcome |",
        "|---|---|",
    ]
    L += [f"| {c} | {pct(m['by_category'][c])} |" for c in CATEGORIES]
    fails = failure_rows(recs)
    L += ["", f"**Failures ({len(fails)})**", ""]
    if fails:
        L += ["| Case | Category | Question | Observed |", "|---|---|---|---|"]
        L += [
            f"| {f['id']}{' †' if f['known_gap'] else ''} | {f['category']} | {f['question'][:70]} | {f['observed']} |"
            for f in fails
        ]
        if any(f["known_gap"] for f in fails):
            L += ["", "† known gap: fails by design, see FAILURE_ANALYSIS.md."]
    else:
        L += ["None."]
    return [x for x in L if x is not None]


def build_report(results: list[Path], out: Path) -> None:
    lines = [
        "# Sageboard — Evaluation summary",
        "",
        f"Generated {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')} by `uv run python -m evals report`. "
        "Every figure below is computed from the result files listed at the end; nothing is typed in by hand.",
        "",
    ]
    used = []
    for path in results:
        if path.suffix == ".jsonl":
            recs = load(path)
            if not recs:
                continue
            mode, scale = recs[0]["mode"], path.stem.split("-")[1]
            lines += [*section(f"Agent pipeline — {path.stem}", mode, scale, recs), ""]
            used.append(path.name)
        elif path.suffix == ".json":
            data = json.loads(path.read_text())
            kind = path.stem.split("-")[0]
            if kind == "safety":
                lines += [*safety_section(data), ""]
            elif kind == "bench":
                lines += [*bench_section(data), ""]
            used.append(path.name)
    lines += ["## Result files", ""] + [f"- `docs/eval/results/{u}`" for u in used]
    out.write_text("\n".join(lines) + "\n")


def safety_section(d: dict[str, Any]) -> list[str]:
    g, i, b = d["guard"], d["isolation"], d["benign"]
    L = [
        "## SQL safety suite",
        "",
        f"- **Guard pass rate:** {g['blocked']}/{g['total']} unsafe statements rejected before reaching the database "
        f"({g['blocked'] / g['total'] * 100:.1f}%). Median validation time {g['median_us']:.0f} µs.",
        f"- **Database isolation (Guard bypassed):** {i['refused_and_unchanged']}/{i['total']} statements in the database-enforced classes "
        "were refused by PostgreSQL itself with tables and row counts unchanged.",
        f"- **False positives:** {b['accepted']}/{b['total']} reference queries accepted by the Guard.",
        "",
        "| Class | Unsafe statements | Rejected by Guard |",
        "|---|---|---|",
    ]
    L += [f"| {k} | {v['n']} | {v['blocked']} |" for k, v in g["by_category"].items()]
    if g["misses"]:
        L += ["", "**Not rejected by the Guard:**", ""] + [
            f"- `{m['sql']}` ({m['category']})" for m in g["misses"]
        ]
    if i["failures"]:
        L += [
            "",
            "**Not refused by the database when the Guard is bypassed (state unchanged in every case):**",
            "",
        ]
        L += [
            f"- `{f['sql']}` → status `{f['status']}`, unchanged={f['unchanged']}"
            for f in i["failures"]
        ]
    if "cost_gate" in d:
        c = d["cost_gate"]
        L += ["", f"**Cost gate:** {c['summary']}"]
    return L


def bench_section(d: dict[str, Any]) -> list[str]:
    L = [
        "## Performance benchmark",
        "",
        f"Scale `{d['scale']}` ({d['rows']}) · {d['repeats']} repetitions per measurement",
        "",
        "| Measurement | p50 | p95 | mean | n |",
        "|---|---|---|---|---|",
    ]
    for name, v in d["measurements"].items():
        L.append(f"| {name} | {v['p50']:.2f} | {v['p95']:.2f} | {v['mean']:.2f} | {v['count']} |")
    for note in d.get("notes", []):
        L += ["", note]
    return L
