from __future__ import annotations

import uuid
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from src.core.db import get_db_instance
from src.core.db.db_models import Job
from src.core.logging import get_logger
from src.services.fetcher import Sample, fetch_instant, fetch_metrics_endpoint
from src.services.metrics_repository import process_samples

logger = get_logger(__name__)

_scheduler: BackgroundScheduler | None = None


def _get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler()
    return _scheduler


def fetch_job_samples(
    prometheus_url: str,
    query: str | None,
    source_type: str,
    offset_seconds: int = 0,
) -> list[Sample]:
    """Fetch samples based on job configuration. Reusable by scheduler and test endpoint."""
    if source_type == "metrics_endpoint":
        metric_filter = query if query else None
        return fetch_metrics_endpoint(target_url=prometheus_url, metric_filter=metric_filter)
    else:
        # source_type == "prometheus"
        query_time = None
        if offset_seconds > 0:
            query_time = datetime.now(timezone.utc).timestamp() - offset_seconds
        return fetch_instant(
            prometheus_url=prometheus_url,
            query=query or "",
            query_time=query_time,
        )


def _execute_job(job_id: uuid.UUID) -> None:
    db = get_db_instance()
    session = db.get_session()
    try:
        job = session.get(Job, job_id)
        if job is None or not job.enabled:
            logger.warning("Job {} not found or disabled, skipping", job_id)
            return

        now = datetime.now(timezone.utc)

        try:
            samples = fetch_job_samples(
                prometheus_url=job.prometheus_url,
                query=job.query,
                source_type=job.source_type,
                offset_seconds=job.offset_seconds,
            )
        except Exception:
            logger.exception("Fetch failed for job {}", job_id)
            return

        process_samples(session, job_id, samples, fetched_at=now)
    finally:
        session.close()


def _job_tick(job_id: uuid.UUID) -> None:
    """Sync wrapper invoked by APScheduler."""
    try:
        _execute_job(job_id)
    except Exception:
        logger.exception("Error in scheduled tick for job {}", job_id)


def add_scheduler_job(job: Job) -> None:
    scheduler = _get_scheduler()
    scheduler_job_id = str(job.id)

    if scheduler.get_job(scheduler_job_id):
        scheduler.remove_job(scheduler_job_id)

    if job.cron_expression:
        trigger = CronTrigger.from_crontab(job.cron_expression)
        scheduler.add_job(
            _job_tick,
            trigger,
            id=scheduler_job_id,
            args=[job.id],
            replace_existing=True,
        )
        logger.info("Scheduled job {} with cron '{}'", job.id, job.cron_expression)
    else:
        scheduler.add_job(
            _job_tick,
            "interval",
            seconds=job.interval_seconds,
            id=scheduler_job_id,
            args=[job.id],
            replace_existing=True,
        )
        logger.info("Scheduled job {} every {}s", job.id, job.interval_seconds)


def remove_scheduler_job(job_id: uuid.UUID) -> None:
    scheduler = _get_scheduler()
    sid = str(job_id)
    if scheduler.get_job(sid):
        scheduler.remove_job(sid)
        logger.info("Removed scheduler job {}", job_id)


def start_scheduler() -> None:
    scheduler = _get_scheduler()

    db = get_db_instance()
    session = db.get_session()
    try:
        result = session.execute(select(Job).where(Job.enabled == True))  # noqa: E712
        jobs = result.scalars().all()
        for job in jobs:
            add_scheduler_job(job)
        logger.info("Loaded {} jobs into scheduler", len(jobs))
    finally:
        session.close()

    scheduler.start()


def stop_scheduler() -> None:
    scheduler = _get_scheduler()
    if scheduler.running:
        scheduler.shutdown(wait=False)
