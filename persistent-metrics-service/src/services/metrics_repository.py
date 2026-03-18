from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.db.db_models import CounterSample, CounterState
from src.core.logging import get_logger
from src.services.fetcher import Sample

logger = get_logger(__name__)


def process_samples(
    session: Session,
    job_id: uuid.UUID,
    samples: list[Sample],
    fetched_at: datetime,
) -> int:
    """Process samples with counter reset detection. Returns number of samples processed."""
    if not samples:
        return 0

    count = 0
    for s in samples:
        stmt = (
            select(CounterState)
            .where(
                CounterState.job_id == job_id,
                CounterState.metric_name == s.metric_name,
                CounterState.labels == s.labels,
            )
            .with_for_update()
        )
        result = session.execute(stmt)
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
            if s.value < state.last_raw_value:
                state.checkpoint += state.last_raw_value
                logger.info(
                    "Counter reset detected for {} {}: checkpoint now {:.2f}",
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

    session.commit()
    logger.info("Processed {} samples for job {}", count, job_id)
    return count
