import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class CounterSample(Base):
    __tablename__ = "counter_samples"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    metric_name: Mapped[str] = mapped_column(String(512), nullable=False)
    labels: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    accumulated_value: Mapped[float] = mapped_column(Float(precision=53), nullable=False)
    raw_value: Mapped[float] = mapped_column(Float(precision=53), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("job_id", "metric_name", "labels", "timestamp", name="uq_counter_sample_dedup"),
    )
