"""Run every case in evals/cases/ against the agent and record the results.

Usage (from backend/): ../.venv/bin/python scripts/run_evals.py [--sleep SECONDS]
"""
import argparse
import asyncio
import json
import math
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from src.agent import tools  # noqa: E402
from src.agent.loop import run_agent  # noqa: E402
from src.config import settings  # noqa: E402
from src.db.session import SessionLocal, engine  # noqa: E402
from src.models.eval import EvalCase, EvalResult, EvalRun  # noqa: E402
from src.models.run import AgentRun, RunStatus  # noqa: E402

EVALS_DIR = Path(__file__).resolve().parents[2] / "evals"


def git_sha() -> str | None:
    root = EVALS_DIR.parent
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=root, capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    return f"{sha}-dirty" if dirty else sha


def percentile(values: list[float], pct: float) -> float | None:
    """Linear-interpolation percentile."""
    if not values:
        return None
    ordered = sorted(values)
    k = (len(ordered) - 1) * pct / 100
    lo, hi = math.floor(k), math.ceil(k)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


async def upsert_case(session, case: dict) -> EvalCase:
    existing = (await session.execute(select(EvalCase).where(EvalCase.slug == case["slug"]))).scalar_one_or_none()
    fields = {
        "repo_url": f"file://evals/fixtures/{case['fixture_dir']}",
        "issue_url": f"https://example.com/issues/{case['slug']}",
        "issue_text": case["issue_text"],
        "expected": {"test_file": case["test_file"], "expected_passed": case["expected_passed"]},
    }
    if existing is None:
        existing = EvalCase(slug=case["slug"], **fields)
        session.add(existing)
    else:
        for key, value in fields.items():
            setattr(existing, key, value)
    await session.commit()
    return existing


async def run_case(session, eval_run: EvalRun, case: dict) -> dict:
    case_row = await upsert_case(session, case)
    fixture = EVALS_DIR / "fixtures" / case["fixture_dir"]
    started = time.perf_counter()
    agent_run_id = None
    steps = 0
    failure_reason = None
    final_passed = False

    with tempfile.TemporaryDirectory(prefix="devpilot_eval_") as tmp:
        workdir = Path(tmp) / "repo"
        shutil.copytree(fixture, workdir)
        tools.FIXTURE_REPO = workdir
        tools.TEST_FILE = case["test_file"]
        try:
            result = await run_agent(
                case_row.issue_url,
                session,
                issue_text=case["issue_text"],
                eval_run_id=eval_run.id,
            )
            agent_run_id, steps = result.run_id, result.steps
            if result.error:
                failure_reason = f"agent error: {result.error}"
        except Exception as exc:  # tolerate anything: a failing case must not abort the run
            await session.rollback()
            failure_reason = f"runner error: {type(exc).__name__}: {exc}"
        # independent check: do not trust the agent's own trace
        check = await tools.run_tests()
        final_passed = bool(check["passed"])
        final_output = check["output"]

    latency_ms = int((time.perf_counter() - started) * 1000)
    passed = final_passed == case["expected_passed"]
    if not passed and failure_reason is None:
        failure_reason = f"tests still failing after {steps} steps: {(final_output.strip().splitlines() or [''])[-1]}"

    if agent_run_id is None:  # EvalResult.agent_run_id is mandatory: record a failed placeholder run
        placeholder = AgentRun(
            issue_url=case_row.issue_url, status=RunStatus.FAILED, eval_run_id=eval_run.id,
            finished_at=datetime.now(timezone.utc),
        )
        session.add(placeholder)
        await session.flush()
        agent_run_id = placeholder.id

    session.add(
        EvalResult(
            eval_run_id=eval_run.id,
            case_id=case_row.id,
            agent_run_id=agent_run_id,
            passed=passed,
            steps=steps,
            latency_ms=latency_ms,
            cost_usd=None,
            failure_reason=failure_reason,
        )
    )
    await session.commit()
    return {
        "slug": case["slug"],
        "passed": passed,
        "steps": steps,
        "latency_ms": latency_ms,
        "cost_usd": None,
        "failure_reason": failure_reason,
        "agent_run_id": str(agent_run_id),
    }


def summarize(details: list[dict]) -> dict:
    total = len(details)
    passed = sum(d["passed"] for d in details)
    latencies = [d["latency_ms"] for d in details]
    steps = [d["steps"] for d in details]
    return {
        "total_cases": total,
        "passed": passed,
        "failed": total - passed,
        "success_rate": round(passed / total, 4) if total else None,
        "avg_steps": round(sum(steps) / total, 2) if total else None,
        "latency_ms_p50": round(percentile(latencies, 50)) if total else None,
        "latency_ms_p95": round(percentile(latencies, 95)) if total else None,
        "cost_usd_per_task": None,  # cost is not computed yet
    }


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sleep", type=float, default=settings.eval_sleep_between_cases_s,
                        help="seconds to wait between cases (free-tier rate limits)")
    parser.add_argument("--only", metavar="SLUG", help="run only the case with this slug (smoke test)")
    args = parser.parse_args()

    cases = [json.loads(p.read_text()) for p in sorted((EVALS_DIR / "cases").glob("*.json"))]
    if args.only:
        cases = [c for c in cases if c["slug"] == args.only]
    if not cases:
        print("no matching cases found in evals/cases/")
        return 1

    original = (tools.FIXTURE_REPO, tools.TEST_FILE)
    async with SessionLocal() as session:
        eval_run = EvalRun(git_sha=git_sha(), model=settings.llm_model)
        session.add(eval_run)
        await session.commit()
        print(f"eval_run {eval_run.id}  model={eval_run.model}  git={eval_run.git_sha}  cases={len(cases)}")

        details = []
        try:
            for i, case in enumerate(cases):
                detail = await run_case(session, eval_run, case)
                details.append(detail)
                mark = "PASS" if detail["passed"] else "FAIL"
                extra = f"  <- {detail['failure_reason']}" if detail["failure_reason"] else ""
                print(f"[{i + 1:02d}/{len(cases)}] {mark} {detail['slug']:26s} "
                      f"steps={detail['steps']} {detail['latency_ms']}ms{extra}", flush=True)
                if i < len(cases) - 1 and args.sleep > 0:
                    await asyncio.sleep(args.sleep)
        finally:
            tools.FIXTURE_REPO, tools.TEST_FILE = original
            await session.rollback()  # the session may be in a failed state after an interrupt
            summary = summarize(details)
            eval_run.finished_at = datetime.now(timezone.utc)
            eval_run.summary = summary
            await session.commit()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = EVALS_DIR / "reports" / f"{stamp}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(
        {"eval_run_id": str(eval_run.id), "model": eval_run.model, "git_sha": eval_run.git_sha,
         "summary": summary, "cases": details}, indent=2) + "\n")

    print("\n== summary ==")
    for key, value in summary.items():
        print(f"{key}: {value}")
    print(f"report: {report_path.relative_to(EVALS_DIR.parent)}")
    await engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
