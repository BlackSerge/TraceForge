import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

if TYPE_CHECKING:
    from src.models.eval import EvalResult, EvalRun
    from src.models.trace import TraceStep


class RunStatus(str, enum.Enum):
    
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED = "failed"


class AgentRun(Base):
    __tablename__ = "agent_run"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    issue_url: Mapped[str] = mapped_column(Text)
    status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus, name="run_status", values_callable=lambda e: [m.value for m in e]),
        default=RunStatus.PENDING,
        server_default=RunStatus.PENDING.value,
    )
    eval_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("eval_run.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))

    steps: Mapped[list["TraceStep"]] = relationship(
        back_populates="run", order_by="TraceStep.step_id", cascade="all, delete-orphan"
    )
    eval_run: Mapped["EvalRun | None"] = relationship(back_populates="agent_runs")
    eval_result: Mapped["EvalResult | None"] = relationship(back_populates="agent_run")
