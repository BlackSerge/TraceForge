import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

if TYPE_CHECKING:
    from src.models.run import AgentRun


class EvalCase(Base):
    __tablename__ = "eval_case"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(Text, unique=True)
    repo_url: Mapped[str] = mapped_column(Text)
    issue_url: Mapped[str | None] = mapped_column(Text)
    issue_text: Mapped[str | None] = mapped_column(Text)
    expected: Mapped[dict[str, Any]] = mapped_column(JSONB)
    tool_tag: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    results: Mapped[list["EvalResult"]] = relationship(back_populates="case")


class EvalRun(Base):
    __tablename__ = "eval_run"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    git_sha: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    results: Mapped[list["EvalResult"]] = relationship(
        back_populates="eval_run", cascade="all, delete-orphan"
    )
    agent_runs: Mapped[list["AgentRun"]] = relationship(back_populates="eval_run")


class EvalResult(Base):
    __tablename__ = "eval_result"
    __table_args__ = (UniqueConstraint("eval_run_id", "case_id", name="uq_eval_result_eval_run_id_case_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    eval_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("eval_run.id", ondelete="CASCADE")
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("eval_case.id", ondelete="RESTRICT"), index=True
    )
    agent_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_run.id", ondelete="RESTRICT"), unique=True
    )
    passed: Mapped[bool] = mapped_column(Boolean)
    steps: Mapped[int] = mapped_column(Integer)
    latency_ms: Mapped[int] = mapped_column(Integer)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6))
    failure_reason: Mapped[str | None] = mapped_column(Text)

    eval_run: Mapped["EvalRun"] = relationship(back_populates="results")
    case: Mapped["EvalCase"] = relationship(back_populates="results")
    agent_run: Mapped["AgentRun"] = relationship(back_populates="eval_result")
