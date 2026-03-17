import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class MetricSample(Base):
    __tablename__ = "metric_samples"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    metric_name: Mapped[str] = mapped_column(String(512), nullable=False)
    labels: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    value: Mapped[float] = mapped_column(Float(precision=53), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("job_id", "metric_name", "labels", "timestamp", name="uq_sample_dedup"),
        Index("ix_metric_latest", "metric_name", "labels"),
        Index("ix_labels_gin", "labels", postgresql_using="gin"),
    )
