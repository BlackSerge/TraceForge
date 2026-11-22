"""Launches a multi-role run in the background. One run at a time: each run spends LLM quota
and starts containers, and the API has no authentication."""
import asyncio
import uuid

from src.agent.demo_repos import temp_workspace
from src.agent.loop import run_multi_agent
from src.db.session import SessionLocal
from src.models.run import AgentRun, RunStatus

_lock = asyncio.Lock()
_tasks: set[asyncio.Task] = set()  # strong references: the loop only keeps weak ones


async def try_reserve() -> bool:
    """Take the single run slot. Acquiring a free asyncio.Lock does not yield, so two requests
    cannot both succeed."""
    if _lock.locked():
        return False
    await _lock.acquire()
    return True


def release() -> None:
    _lock.release()


async def _execute(run_id: uuid.UUID, issue_text: str, repo: dict) -> None:
    try:
        async with SessionLocal() as session:
            with temp_workspace(repo) as ws:
                await run_multi_agent(
                    f"manual://{repo['slug']}", session, issue_text=issue_text, workspace=ws, run_id=run_id
                )
    except Exception as exc:  # never leave the run in running/pending
        async with SessionLocal() as session:
            run = await session.get(AgentRun, run_id)
            if run is not None and run.status in (RunStatus.PENDING, RunStatus.RUNNING):
                run.status = RunStatus.FAILED
                run.rejection_reason = f"Internal error: {type(exc).__name__}: {exc}"
                await session.commit()
    finally:
        _lock.release()


def start(run_id: uuid.UUID, issue_text: str, repo: dict) -> None:
    """Run in the background; the task releases the slot taken with try_reserve()."""
    task = asyncio.create_task(_execute(run_id, issue_text, repo))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
