from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_session
from src.models.trace import TraceStep
from src.schemas.trace import TraceStepRead

router = APIRouter(prefix="/traces", tags=["traces"])


@router.get("", response_model=list[TraceStepRead])
async def list_traces(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(TraceStep).order_by(TraceStep.timestamp.desc()).limit(50)
    )
    return result.scalars().all()
