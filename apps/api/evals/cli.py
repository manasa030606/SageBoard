from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from app.core.config import Settings, get_settings

OUT = Path(__file__).resolve().parents[3] / "docs" / "eval" / "results"


def settings_for(mode: str, db: str, scale: str) -> Settings:
    if db == "test":
        from tests.conftest import make_settings

        return make_settings(
            database_url=os.environ["SAGEBOARD_TEST_DATABASE_URL"],
            ingest_database_url=os.environ["SAGEBOARD_TEST_INGEST_DATABASE_URL"],
            executor_database_url=os.environ["SAGEBOARD_TEST_EXECUTOR_DATABASE_URL"],
            upload_dir=Path(tempfile.mkdtemp()),
            demo_dataset_scale=scale,
        )
    return get_settings().model_copy(update={"demo_dataset_scale": scale})


def _run(args: argparse.Namespace) -> None:
    from evals.harness import run_eval

    db = args.db or ("test" if args.mode == "oracle" else "dev")
    settings = settings_for(args.mode, db, args.scale)
    if args.mode == "live" and settings.llm_provider == "mock":
        sys.exit(
            "Live mode needs LLM_PROVIDER/LLM_MODEL/API key in apps/api/.env (provider is 'mock')."
        )
    out = args.out or OUT / f"{args.mode}-{args.scale}.jsonl"
    recs = run_eval(
        settings,
        mode=args.mode,
        scale=args.scale,
        out=out,
        ids=args.ids.split(",") if args.ids else None,
        resume=args.resume,
        max_cases=args.max_cases,
    )
    print(f"{len(recs)} records -> {out}")


def _write_json(name: str, data: object) -> None:
    out = OUT / name
    out.write_text(json.dumps(data, indent=2, default=str))
    print(f"wrote {out}")


def _safety(args: argparse.Namespace) -> None:
    from evals.safety import run_safety

    _write_json(
        f"safety-{args.scale}.json",
        run_safety(settings_for("oracle", "test", args.scale), args.scale),
    )


def _bench(args: argparse.Namespace) -> None:
    from evals.bench import run_bench

    data = run_bench(settings_for("oracle", "test", args.scale), args.scale, args.repeats)
    _write_json(f"bench-{args.scale}.json", data)


def _dataset(args: argparse.Namespace) -> None:
    from evals.export import export_dataset

    out = OUT.parent / "dataset" / f"retail_v1.{args.scale}.json"
    print(f"{export_dataset(args.scale, out)} cases -> {out}")


def _report(args: argparse.Namespace) -> None:
    from evals.report import build_report

    build_report(args.results, args.out)
    print(f"wrote {args.out}")


def main() -> None:
    p = argparse.ArgumentParser(prog="python -m evals")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run the cases through the API")
    r.add_argument("--mode", choices=["oracle", "live"], required=True)
    r.add_argument("--db", choices=["test", "dev"], help="default: test for oracle, dev for live")
    r.add_argument("--scale", choices=["small", "standard"], default="small")
    r.add_argument("--ids", help="comma-separated case ids")
    r.add_argument("--resume", action="store_true")
    r.add_argument("--max-cases", type=int)
    r.add_argument("--out", type=Path)
    sf = sub.add_parser("safety", help="SQL safety suite (Guard + database isolation)")
    sf.add_argument("--scale", choices=["small", "standard"], default="small")
    d = sub.add_parser("dataset", help="export the questions and expected results as JSON")
    d.add_argument("--scale", choices=["small", "standard"], default="standard")
    b = sub.add_parser("bench", help="performance benchmark")
    b.add_argument("--scale", choices=["small", "standard"], default="small")
    b.add_argument("--repeats", type=int, default=5)
    s = sub.add_parser("report", help="build the summary from result files")
    s.add_argument("--results", type=Path, nargs="+", required=True)
    s.add_argument("--out", type=Path, default=OUT.parent / "EVALUATION_SUMMARY.md")
    args = p.parse_args()
    {"run": _run, "safety": _safety, "dataset": _dataset, "bench": _bench, "report": _report}[
        args.cmd
    ](args)
