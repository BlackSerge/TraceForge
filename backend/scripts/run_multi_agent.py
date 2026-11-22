"""Ad-hoc multi-role smoke test: `PYTHONPATH=. python scripts/run_multi_agent.py case_slug [...]`."""
import asyncio
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from src.agent import tools  # noqa: E402
from src.agent.loop import run_multi_agent  # noqa: E402
from src.db.session import SessionLocal, engine  # noqa: E402
from src.models.trace import TraceStep  # noqa: E402

EVALS = Path(__file__).resolve().parents[2] / "evals"


async def run_case(slug: str) -> None:
    case = next(
        json.loads(p.read_text()) for p in sorted((EVALS / "cases").glob("*.json"))
        if json.loads(p.read_text())["slug"] == slug
    )
    with tempfile.TemporaryDirectory(prefix="devpilot_multi_") as tmp:
        repo = Path(tmp) / "repo"
        shutil.copytree(EVALS / "fixtures" / case["fixture_dir"], repo)
        tools.FIXTURE_REPO, tools.TEST_FILE = repo, case["test_file"]
        async with SessionLocal() as session:
            res = await run_multi_agent(f"https://example.com/issues/{slug}", session, issue_text=case["issue_text"])
            steps = (await session.execute(
                select(TraceStep).where(TraceStep.run_id == res.run_id).order_by(TraceStep.step_id)
            )).scalars().all()
        check = await tools.run_tests()
    print(f"\n=== {slug}  run={res.run_id}")
    for s in steps:
        calls = ", ".join(
            f"{c['name']}({c['args'].get('path') or c['args'].get('file') or c['args'].get('verdict') or ''})"
            for c in s.tool_calls
        )
        print(f"  step {s.step_id:>2} [{s.agent_role:<9}] {s.outcome.value:<8} {calls or '-'}")
    print("  triage:", res.triage)
    print("  review:", res.review)
    print("  status:", res.status.value, "| independent pytest passed:", check["passed"], "| error:", res.error)


async def main() -> None:
    for slug in sys.argv[1:]:
        await run_case(slug)
    await engine.dispose()


asyncio.run(main())
