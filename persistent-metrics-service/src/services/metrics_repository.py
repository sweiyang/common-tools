from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.metric_sample import MetricSample

logger = logging.getLogger(__name__)


async def bulk_insert_samples(
    session: AsyncSession,
    job_id,
    samples: list,
    fetched_at: datetime,
) -> int:
    """Insert samples with ON CONFLICT DO NOTHING dedup. Returns rows inserted."""
    if not samples:
        return 0

    rows = [
        {
            "job_id": job_id,
            "metric_name": s.metric_name,
            "labels": s.labels,
            "value": s.value,
            "timestamp": s.timestamp,
            "fetched_at": fetched_at,
        }
        for s in samples
    ]

    stmt = (
        pg_insert(MetricSample)
        .values(rows)
        .on_conflict_do_nothing(constraint="uq_sample_dedup")
    )
    result = await session.execute(stmt)
    await session.commit()

    inserted = result.rowcount  # type: ignore[union-attr]
    logger.info("Inserted %d / %d samples for job %s", inserted, len(rows), job_id)
    return inserted


async def update_last_queried_at(
    session: AsyncSession,
    job_id,
    queried_at: datetime,
) -> None:
    await session.execute(
        text("UPDATE jobs SET last_queried_at = :ts, updated_at = now() WHERE id = :jid"),
        {"ts": queried_at, "jid": str(job_id)},
    )
    await session.commit()
