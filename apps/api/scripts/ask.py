"""Ask the agent a question from the terminal and print its trace (real model only).

Uses the same runner as the API: the configured LLM provider, the stored catalog, the
SQL Guard and the read-only executor. The question is saved as a normal analysis
session, so it also appears in History.

    uv run python scripts/ask.py --email you@example.com "Why did revenue drop last month?"
    uv run python scripts/ask.py --email you@example.com --dataset "Sample" "Top 5 products by revenue"

Requires LLM_PROVIDER, LLM_MODEL and the provider's API key in apps/api/.env.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from sqlalchemy import func, select

from app.agent.llm.factory import NOT_CONFIGURED_MESSAGE, build_llm
from app.agent.runner import AgentRunner
from app.core.config import get_settings
from app.db.engines import open_databases
from app.db.models import AgentNodeRun, AnalysisSession, Dataset, User
from app.services.analysis import AnalysisService


async def main(email: str, dataset_name: str | None, question: str) -> int:
    settings = get_settings()
    llm = build_llm(settings)
    if llm is None:
        print(NOT_CONFIGURED_MESSAGE, file=sys.stderr)
        return 2
    databases = await open_databases(settings)
    try:
        if databases.sessions is None or databases.executor is None:
            print("DATABASE_URL and EXECUTOR_DATABASE_URL must be set.", file=sys.stderr)
            return 2
        async with databases.sessions() as db:
            user = await db.scalar(select(User).where(func.lower(User.email) == email.lower()))
            if user is None:
                print(f"No account for {email}. Sign up in the web app first.", file=sys.stderr)
                return 2
            stmt = select(Dataset).where(Dataset.owner_id == user.id, Dataset.status == "ready")
            if dataset_name:
                stmt = stmt.where(Dataset.name.ilike(f"%{dataset_name}%"))
            dataset = await db.scalar(stmt.order_by(Dataset.created_at.desc()))
            if dataset is None:
                print(
                    "No ready dataset found. Add the sample dataset in Data sources first.",
                    file=sys.stderr,
                )
                return 2
            service = AnalysisService(db)
            convo = await service.create_conversation(user, dataset_id=dataset.id, title=None)
            run = await service.create_session(user, convo.id, question)
            session_id = run.id
        print(
            f"Dataset: {dataset.name} · model: {llm.label[0]}/{llm.label[1]} · session {session_id}\n"
        )

        await AgentRunner(databases=databases, settings=settings, llm=llm).run(session_id)

        async with databases.sessions() as db:
            nodes = (
                await db.scalars(
                    select(AgentNodeRun)
                    .where(AgentNodeRun.analysis_session_id == session_id)
                    .order_by(AgentNodeRun.seq)
                )
            ).all()
            for n in nodes:
                print(
                    f"{n.seq:>3} {n.node:<23} {n.status:<9} {n.duration_ms:>6} ms  {json.dumps(n.summary, default=str)[:110]}"
                )
                if n.error:
                    print(f"      ! {n.error}")
            done = await db.get(AnalysisSession, session_id)
            if done is None:
                return 1
            result = done.result or {}
            response = result.get("response", {})
            print(
                f"\nStatus: {done.status} ({done.termination_reason}) · {done.llm_calls} model calls · "
                f"{done.sql_executions} queries · {done.tokens_in}+{done.tokens_out} tokens · {done.duration_ms} ms\n"
            )
            print(response.get("summary") or done.error_message or "")
            for finding in response.get("key_findings", []):
                print(f"  • {finding['headline']}")
            for caveat in response.get("caveats", []):
                print(f"  ⚠ {caveat}")
            for step in result.get("steps", []):
                print(
                    f"\n[{step['step_id']}] {step['purpose']} — {step['status']}\n{step.get('sql') or step.get('failure_explanation')}"
                )
        return 0
    finally:
        await databases.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("question")
    parser.add_argument("--email", required=True, help="the account that owns the dataset")
    parser.add_argument("--dataset", help="part of the dataset name (default: most recent)")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.email, args.dataset, args.question)))
