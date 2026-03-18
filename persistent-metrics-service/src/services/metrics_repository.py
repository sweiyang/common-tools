from __future__ import annotations

import logging
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.counter_sample import CounterSample
from src.models.counter_state import CounterState
from src.services.fetcher import Sample

logger = logging.getLogger(__name__)


async def process_samples(
    session: AsyncSession,
    job_id: uuid.UUID,
    samples: list[Sample],
    fetched_at: datetime,
) -> int:
    """Process samples with counter reset detection. Returns number of samples processed."""
    if not samples:
        return 0

    count = 0
    for s in samples:
        # Lock the counter state row for this series
        stmt = (
            select(CounterState)
            .where(
                CounterState.job_id == job_id,
                CounterState.metric_name == s.metric_name,
                CounterState.labels == s.labels,
            )
            .with_for_update()
        )
        result = await session.execute(stmt)
        state = result.scalar_one_or_none()

        if state is None:
            state = CounterState(
                job_id=job_id,
                metric_name=s.metric_name,
                labels=s.labels,
                last_raw_value=s.value,
                checkpoint=0.0,
            )
            session.add(state)
        else:
            # Reset detection: if new value < last raw value, counter was reset
            if s.value < state.last_raw_value:
                state.checkpoint += state.last_raw_value
                logger.info(
                    "Counter reset detected for %s %s: checkpoint now %.2f",
                    s.metric_name, s.labels, state.checkpoint,
                )
            state.last_raw_value = s.value

        accumulated = state.checkpoint + s.value

        sample = CounterSample(
            job_id=job_id,
            metric_name=s.metric_name,
            labels=s.labels,
            accumulated_value=accumulated,
            raw_value=s.value,
            timestamp=s.timestamp,
            fetched_at=fetched_at,
        )
        session.add(sample)
        count += 1

    await session.commit()
    logger.info("Processed %d samples for job %s", count, job_id)
    return count
