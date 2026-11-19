import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from src.models.run import RunStatus
from src.schemas.trace import TraceStepRead


class AgentRunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    issue_url: str
    status: RunStatus
    created_at: datetime
    finished_at: datetime | None
    total_cost_usd: Decimal | None
    rejection_reason: str | None


class AgentRunDetail(AgentRunSummary):
    steps: list[TraceStepRead]


class RejectRequest(BaseModel):
    reason: str | None = None
