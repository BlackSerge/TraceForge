from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_session
from src.models.trace import TraceStep
from src.schemas.trace import TraceStepSummary

router = APIRouter(prefix="/traces", tags=["traces"])


@router.get("", response_model=list[TraceStepSummary])
async def list_traces(session: AsyncSession = Depends(get_session)):
    """Latest 50 steps without input_context (fetch it per step: GET /agent/runs/{id}/steps/{n})."""
    result = await session.execute(
        select(TraceStep).order_by(TraceStep.timestamp.desc()).limit(50)
    )
    return result.scalars().all()
