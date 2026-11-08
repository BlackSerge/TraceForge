import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict

from src.models.trace import StepOutcome


class TraceStepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    step_id: int
    timestamp: datetime
    agent_role: str
    input_context: dict[str, Any]
    tool_calls: list[dict[str, Any]]
    reasoning_summary: str
    outcome: StepOutcome
    attempt: int
    latency_ms: int | None
    tokens_in: int | None
    tokens_out: int | None
    cost_usd: Decimal | None
    model: str | None
