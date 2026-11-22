import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.session import get_session
from src.models.run import AgentRun, RunStatus
from src.models.trace import TraceStep
from src.agent import executor
from src.agent.demo_repos import find_demo_repo, list_demo_repos
from src.schemas.agent import (
    AgentRunDetail, AgentRunSummary, CreateRunRequest, DemoRepo, RejectRequest,
)
from src.schemas.trace import TraceStepRead

router = APIRouter(prefix="/agent", tags=["agent"])


@router.get("/demo-repos", response_model=list[DemoRepo])
async def demo_repos():
    return [DemoRepo(**{k: r[k] for k in ("slug", "description", "example_issue")}) for r in list_demo_repos()]


@router.post("/runs", response_model=AgentRunSummary, status_code=202)
async def create_run(body: CreateRunRequest, session: AsyncSession = Depends(get_session)):
    """Start a Triage -> Developer -> Reviewer run in the background; poll GET /agent/runs/{id}."""
    repo = find_demo_repo(body.repo)
    if repo is None:
        raise HTTPException(status_code=404, detail="Unknown demo repo")
    if not await executor.try_reserve():
        raise HTTPException(status_code=429, detail="A run is already in progress")
    try:
        run = AgentRun(issue_url=f"manual://{repo['slug']}", status=RunStatus.PENDING, issue_text=body.issue_text)
        session.add(run)
        await session.commit()
    except Exception:
        executor.release()
        raise
    executor.start(run.id, body.issue_text, repo)
    return run


@router.get("/runs", response_model=list[AgentRunSummary])
async def list_runs(
    status: RunStatus | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    query = select(AgentRun).order_by(AgentRun.created_at.desc()).limit(limit).offset(offset)
    if status is not None:
        query = query.where(AgentRun.status == status)
    return (await session.execute(query)).scalars().all()


@router.get("/runs/{run_id}", response_model=AgentRunDetail)
async def get_run(run_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    run = (
        await session.execute(
            select(AgentRun).where(AgentRun.id == run_id).options(selectinload(AgentRun.steps))
        )
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.delete("/runs/{run_id}", status_code=204)
async def delete_run(run_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    """Delete a run and its trace steps. Refused while the agent is working on it, and for runs that
    belong to an eval run (their results reference them)."""
    run = await session.get(AgentRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status in (RunStatus.PENDING, RunStatus.RUNNING):
        raise HTTPException(status_code=409, detail="Run is in progress")
    if run.eval_run_id is not None:
        raise HTTPException(status_code=409, detail="Run belongs to an eval run")
    await session.delete(run)
    await session.commit()


@router.get("/runs/{run_id}/steps/{step_id}", response_model=TraceStepRead)
async def get_step(run_id: uuid.UUID, step_id: int, session: AsyncSession = Depends(get_session)):
    """Full step including input_context (omitted from the run detail to keep it small)."""
    step = (
        await session.execute(select(TraceStep).where(TraceStep.run_id == run_id, TraceStep.step_id == step_id))
    ).scalar_one_or_none()
    if step is None:
        raise HTTPException(status_code=404, detail="Step not found")
    return step


async def _decide(
    run_id: uuid.UUID, session: AsyncSession, new_status: RunStatus, rejection_reason: str | None = None
) -> AgentRun:
    """Move a run out of awaiting_approval. The conditional UPDATE makes the transition
    atomic: if two requests race, only one matches the WHERE clause."""
    result = await session.execute(
        update(AgentRun)
        .where(AgentRun.id == run_id, AgentRun.status == RunStatus.AWAITING_APPROVAL)
        .values(status=new_status, finished_at=datetime.now(timezone.utc), rejection_reason=rejection_reason)
    )
    await session.commit()
    if result.rowcount == 0:
        exists = (await session.execute(select(AgentRun.id).where(AgentRun.id == run_id))).scalar_one_or_none()
        if exists is None:
            raise HTTPException(status_code=404, detail="Run not found")
        raise HTTPException(status_code=400, detail="Run is not awaiting approval")
    return (await session.execute(select(AgentRun).where(AgentRun.id == run_id))).scalar_one()


@router.post("/runs/{run_id}/approve", response_model=AgentRunSummary)
async def approve_run(run_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    # Approving only records the human decision: the agent never merges.
    return await _decide(run_id, session, RunStatus.APPROVED)


@router.post("/runs/{run_id}/reject", response_model=AgentRunSummary)
async def reject_run(run_id: uuid.UUID, body: RejectRequest, session: AsyncSession = Depends(get_session)):
    return await _decide(run_id, session, RunStatus.REJECTED, body.reason)
