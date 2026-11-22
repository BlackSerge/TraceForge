import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from src.models.run import RunStatus
from src.schemas.trace import TraceStepSummary


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
    steps: list[TraceStepSummary]


class RejectRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)
