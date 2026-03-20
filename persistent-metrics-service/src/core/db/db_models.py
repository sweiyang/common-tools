import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.db.db import Base


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    query: Mapped[str] = mapped_column(String(4096), nullable=False)
    interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    offset_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cron_expression: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, default="prometheus")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CounterState(Base):
    __tablename__ = "counter_states"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    metric_name: Mapped[str] = mapped_column(String(512), nullable=False)
    labels: Mapped[str] = mapped_column(Text, nullable=False, server_default="{}")
    current_value: Mapped[float] = mapped_column(Float(precision=53), nullable=False)
    checkpoint: Mapped[float] = mapped_column(Float(precision=53), nullable=False, server_default="0.0")
    count: Mapped[float] = mapped_column(Float(precision=53), nullable=False, server_default="0.0")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("job_id", "metric_name", "labels", name="uq_counter_state"),
    )
