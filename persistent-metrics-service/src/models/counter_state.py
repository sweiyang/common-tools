import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class CounterState(Base):
    __tablename__ = "counter_states"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    metric_name: Mapped[str] = mapped_column(String(512), nullable=False)
    labels: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    last_raw_value: Mapped[float] = mapped_column(Float(precision=53), nullable=False)
    checkpoint: Mapped[float] = mapped_column(Float(precision=53), nullable=False, server_default="0.0")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("job_id", "metric_name", "labels", name="uq_counter_state"),
        Index("ix_counter_labels_gin", "labels", postgresql_using="gin"),
    )
