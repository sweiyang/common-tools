from __future__ import annotations

import json
import uuid

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from src.core.db.db_models import CounterState, Job
from src.services.fetcher import Sample


def _canonical_labels(labels: dict) -> str:
    return json.dumps(labels, sort_keys=True, separators=(",", ":"))


def check_metric_conflicts(
    session: Session,
    samples: list[Sample],
    exclude_job_id: uuid.UUID | None = None,
) -> list[dict]:
    """Check if any of the given samples conflict with existing counter_states from other jobs.

    Returns a list of conflict dicts with details about the conflicting job.
    """
    # Extract unique (metric_name, canonical_labels) pairs
    unique_keys: set[tuple[str, str]] = set()
    for s in samples:
        unique_keys.add((s.metric_name, _canonical_labels(s.labels)))

    if not unique_keys:
        return []

    conflicts: list[dict] = []

    # Query in batches to avoid overly large IN clauses
    metric_names = list({k[0] for k in unique_keys})

    stmt = (
        select(CounterState, Job.name, Job.application_name)
        .join(Job, CounterState.job_id == Job.id)
        .where(CounterState.metric_name.in_(metric_names))
    )
    if exclude_job_id is not None:
        stmt = stmt.where(CounterState.job_id != exclude_job_id)

    rows = session.execute(stmt).all()

    for counter_state, job_name, app_name in rows:
        key = (counter_state.metric_name, counter_state.labels)
        if key in unique_keys:
            conflicts.append({
                "metric_name": counter_state.metric_name,
                "labels": json.loads(counter_state.labels),
                "existing_job_id": str(counter_state.job_id),
                "existing_job_name": job_name,
                "existing_application_name": app_name,
            })

    return conflicts
