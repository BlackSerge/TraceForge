import time
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.agent import tools
from src.models.run import AgentRun, RunStatus
from src.models.trace import StepOutcome, TraceStep

MAX_ATTEMPTS = 3
MOCK_PATH = "sample.py"
MOCK_CONTENT = "def add(a, b):\n    return a + b\n"


async def run_agent(issue_url: str, session: AsyncSession) -> uuid.UUID:
    run = AgentRun(issue_url=issue_url, status=RunStatus.RUNNING)
    session.add(run)
    await session.commit()

    passed = False
    for attempt in range(1, MAX_ATTEMPTS + 1):
        started = time.perf_counter()
        read_args = {"path": MOCK_PATH}
        read_result = await tools.read_file(**read_args)
        patch_args = {"file": MOCK_PATH, "new_content": MOCK_CONTENT}
        patch_result = await tools.propose_patch(**patch_args)
        test_result = await tools.run_tests()
        latency_ms = int((time.perf_counter() - started) * 1000)
        passed = bool(test_result["passed"])

        session.add(
            TraceStep(
                run_id=run.id,
                step_id=attempt,
                agent_role="coder",
                input_context={
                    "issue_url": issue_url,
                    "read_file": read_args,
                    "propose_patch": patch_args,
                    "run_tests": {},
                },
                tool_calls=[
                    {"name": "read_file", "args": read_args, "result": read_result},
                    {"name": "propose_patch", "args": patch_args, "result": patch_result},
                    {"name": "run_tests", "args": {}, "result": test_result},
                ],
                reasoning_summary=f"mock decision: attempt {attempt}",
                outcome=StepOutcome.SUCCESS if passed else StepOutcome.RETRY,
                attempt=attempt,
                latency_ms=latency_ms,
            )
        )
        await session.commit()
        if passed:
            break

    run.status = RunStatus.AWAITING_APPROVAL if passed else RunStatus.FAILED
    run.finished_at = datetime.now(timezone.utc)
    await session.commit()
    return run.id
