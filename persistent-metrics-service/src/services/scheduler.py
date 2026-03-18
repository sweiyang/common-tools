from __future__ import annotations

import uuid
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

from src.core.db import get_db_instance
from src.core.db.db_models import Job
from src.core.logging import get_logger
from src.services.fetcher import fetch_instant
from src.services.metrics_repository import process_samples

logger = get_logger(__name__)

_scheduler: BackgroundScheduler | None = None


def _get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler()
    return _scheduler


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
            samples = fetch_instant(
                prometheus_url=job.prometheus_url,
                query=job.query,
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
