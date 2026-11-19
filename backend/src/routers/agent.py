import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.session import get_session
from src.models.run import AgentRun, RunStatus
from src.schemas.agent import AgentRunDetail, AgentRunSummary, RejectRequest

router = APIRouter(prefix="/agent", tags=["agent"])


@router.get("/runs", response_model=list[AgentRunSummary])
async def list_runs(status: RunStatus | None = None, session: AsyncSession = Depends(get_session)):
    query = select(AgentRun).order_by(AgentRun.created_at.desc())
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
