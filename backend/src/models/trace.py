import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

if TYPE_CHECKING:
    from src.models.run import AgentRun


class StepOutcome(str, enum.Enum):
    SUCCESS = "success"
    ERROR = "error"
    RETRY = "retry"
    STOPPED = "stopped"


class TraceStep(Base):
    __tablename__ = "trace_step"
    __table_args__ = (UniqueConstraint("run_id", "step_id", name="uq_trace_step_run_id_step_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_run.id", ondelete="CASCADE")
    )
    step_id: Mapped[int] = mapped_column(Integer)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    agent_role: Mapped[str] = mapped_column(Text, default="coder", server_default="coder")
    input_context: Mapped[dict[str, Any]] = mapped_column(JSONB)
    tool_calls: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    reasoning_summary: Mapped[str] = mapped_column(Text, default="", server_default="")
    outcome: Mapped[StepOutcome] = mapped_column(
        Enum(StepOutcome, name="step_outcome", values_callable=lambda e: [m.value for m in e])
    )
    attempt: Mapped[int] = mapped_column(SmallInteger, default=1, server_default="1")
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    tokens_in: Mapped[int | None] = mapped_column(Integer)
    tokens_out: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    model: Mapped[str | None] = mapped_column(Text)

    run: Mapped["AgentRun"] = relationship(back_populates="steps")
