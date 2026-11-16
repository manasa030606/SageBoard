"""Measure a running API: endpoint latency, concurrency, agent timing and CSV upload.

Reproducible against the browser-test backend (real API, PostgreSQL and pipeline; the
model is the oracle, so agent timings measure the pipeline, not a live model):

    E2E_REGISTRATIONS_PER_HOUR=1000 uv run python -m evals.e2e_server 8100
    uv run python scripts/perf_probe.py http://localhost:8100/api/v1

Prints a JSON report. Nothing here is estimated: every figure is a measured wall time.
"""

from __future__ import annotations

import asyncio
import json
import multiprocessing
import statistics
import sys
import tempfile
import time
import uuid
from typing import Any

import httpx

PASSWORD = "correct horse battery staple 9"  # noqa: S105 - a throwaway test account
HTTP_ERROR = 300
QUESTIONS = ["What is the total revenue?", "What is our profit margin by product category?"]


def _ping(base: str, stop: Any, out: Any) -> None:
    """Runs in its own process, so the measurement is not slowed by this script's own work."""
    samples: list[float] = []
    with httpx.Client(base_url=base, timeout=60) as client:
        while not stop.is_set():
            start = time.perf_counter()
            client.get("/healthz")
            samples.append((time.perf_counter() - start) * 1000)
            time.sleep(0.05)
    out.put(samples)


def pct(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int(len(ordered) * p))], 1)


def summary(ms: list[float]) -> dict[str, float | int]:
    return {
        "n": len(ms),
        "p50_ms": pct(ms, 0.5),
        "p95_ms": pct(ms, 0.95),
        "max_ms": round(max(ms), 1),
        "mean_ms": round(statistics.mean(ms), 1),
    }


async def new_user(base: str, label: str) -> httpx.AsyncClient:
    client = httpx.AsyncClient(base_url=base, timeout=180)
    r = await client.post(
        "/auth/register",
        json={
            "email": f"{label}-{uuid.uuid4().hex[:10]}@example.test",
            "password": PASSWORD,
            "full_name": label,
        },
    )
    r.raise_for_status()
    client.headers["X-CSRF-Token"] = r.json()["csrf_token"]
    return client


async def timed(
    client: httpx.AsyncClient, method: str, url: str, **kw: object
) -> tuple[float, int]:
    start = time.perf_counter()
    r = await client.request(method, url, **kw)  # type: ignore[arg-type]
    return (time.perf_counter() - start) * 1000, r.status_code


async def ask(client: httpx.AsyncClient, dataset_id: str, question: str) -> dict[str, object]:
    start = time.perf_counter()
    convo = (await client.post("/conversations", json={"dataset_id": dataset_id})).json()
    accepted = (
        await client.post(f"/conversations/{convo['id']}/sessions", json={"question": question})
    ).json()
    sid = accepted["session"]["id"]
    while True:
        detail = (await client.get(f"/analysis-sessions/{sid}")).json()
        if detail["status"] not in ("queued", "running"):
            break
        await asyncio.sleep(0.2)
    trace = (await client.get(f"/analysis-sessions/{sid}/trace")).json()
    nodes = trace["items"] if isinstance(trace, dict) and "items" in trace else trace
    return {
        "wall_ms": round((time.perf_counter() - start) * 1000),
        "status": detail["status"],
        "llm_calls": detail["llm_calls"],
        "sql_executions": detail["sql_executions"],
        "tokens_in": detail["tokens_in"],
        "tokens_out": detail["tokens_out"],
        "node_ms": {n["node"]: n["duration_ms"] for n in nodes},
    }


async def csv_section(base: str, user: httpx.AsyncClient) -> dict[str, object]:
    """Upload and load a 20 MB CSV while another process polls /healthz."""
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(b"id,amount,label,note\n")
        i = 0
        while f.tell() < 20 * 1024 * 1024:
            f.write(
                "".join(
                    f"{i + j},{(i + j) % 997}.5,item-{(i + j) % 50},some free text note number {i + j}\n"
                    for j in range(2000)
                ).encode()
            )
            i += 2000
        path = f.name
    stop = multiprocessing.Event()
    queue: Any = multiprocessing.Queue()
    pinger = multiprocessing.Process(target=_ping, args=(base, stop, queue))
    pinger.start()
    with open(path, "rb") as fh:  # noqa: ASYNC230 - a one-off script, not a server
        start = time.perf_counter()
        r = await user.post("/datasets/uploads", files={"file": ("big.csv", fh, "text/csv")})
        upload_s = time.perf_counter() - start
    body = r.json()
    finalize_s = None
    if r.status_code < HTTP_ERROR:
        start = time.perf_counter()
        fin = await user.post(
            f"/datasets/{body['dataset']['id']}/finalize", json={"column_types": {}}
        )
        finalize_s = round(time.perf_counter() - start, 2)
        body = {
            "finalize_status": fin.status_code,
            "rows": fin.json().get("dataset", {}).get("total_rows"),
        }
    stop.set()
    during: list[float] = queue.get()
    pinger.join()
    return {
        "healthz_during_upload_and_finalize": summary(during),
        "upload_status": r.status_code,
        "upload_review_s": round(upload_s, 2),
        "finalize_s": finalize_s,
        "result": body,
    }


async def main(base: str) -> None:
    report: dict[str, object] = {"base": base}
    user = await new_user(base, "perf")
    demo = (await user.post("/datasets/demo")).json()["dataset"]
    ds = demo["id"]

    # 1. Sequential latency of read endpoints.
    endpoints = {
        "GET /healthz": "/healthz",
        "GET /auth/me": "/auth/me",
        "GET /datasets": "/datasets",
        "GET /datasets/{id}/schema": f"/datasets/{ds}/schema",
        "GET /conversations": "/conversations",
        "GET /history/sessions": "/history/sessions",
        "GET /history/queries": "/history/queries",
        "GET /reports": "/reports",
    }
    latency: dict[str, object] = {}
    for label, url in endpoints.items():
        samples = [(await timed(user, "GET", url))[0] for _ in range(100)]
        latency[label] = summary(samples)
    report["sequential_latency"] = latency

    # 2. Concurrency: 20 signed-in users, each issuing 25 mixed reads at once.
    users = [await new_user(base, f"c{i}") for i in range(20)]

    async def burst(c: httpx.AsyncClient) -> list[tuple[float, int]]:
        urls = ["/auth/me", "/datasets", "/conversations", "/history/sessions", "/reports"] * 5
        return [await timed(c, "GET", u) for u in urls]

    start = time.perf_counter()
    results = [r for batch in await asyncio.gather(*(burst(c) for c in users)) for r in batch]
    elapsed = time.perf_counter() - start
    codes: dict[str, int] = {}
    for _, code in results:
        codes[str(code)] = codes.get(str(code), 0) + 1
    report["concurrent_reads"] = {
        "users": len(users),
        "requests": len(results),
        "elapsed_s": round(elapsed, 2),
        "throughput_rps": round(len(results) / elapsed, 1),
        "status_codes": codes,
        **summary([ms for ms, _ in results]),
    }

    # 3. Agent pipeline, one user, sequential (oracle model).
    report["agent_sequential"] = [await ask(user, ds, QUESTIONS[0]) for _ in range(3)]
    report["agent_refusal"] = await ask(user, ds, QUESTIONS[1])

    # 4. Agent under load: 8 users ask at once (the server runs 4 at a time).
    loaded = []
    for c in users[:8]:
        loaded.append((c, (await c.post("/datasets/demo")).json()["dataset"]["id"]))
    start = time.perf_counter()
    answers = await asyncio.gather(*(ask(c, d, QUESTIONS[0]) for c, d in loaded))
    report["agent_concurrent_8"] = {
        "elapsed_s": round(time.perf_counter() - start, 2),
        "statuses": [a["status"] for a in answers],
        **summary([float(a["wall_ms"]) for a in answers]),  # type: ignore[arg-type]
    }

    report["csv_20mb"] = await csv_section(base, user)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8100/api/v1"))
