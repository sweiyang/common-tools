from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

from src.core.database import async_session
from src.models.job import Job
from src.services.fetcher import fetch_instant
from src.services.metrics_repository import process_samples

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None
_loop: asyncio.AbstractEventLoop | None = None


def _get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler()
    return _scheduler


def _run_async(coro):
    """Run an async coroutine from the sync APScheduler thread."""
    loop = _loop or asyncio.new_event_loop()
    return loop.run_until_complete(coro)


async def _execute_job(job_id: uuid.UUID) -> None:
    async with async_session() as session:
        job = await session.get(Job, job_id)
        if job is None or not job.enabled:
            logger.warning("Job %s not found or disabled, skipping", job_id)
            return

        now = datetime.now(timezone.utc)

        try:
            samples = await fetch_instant(
                prometheus_url=job.prometheus_url,
                query=job.query,
            )
        except Exception:
            logger.exception("Fetch failed for job %s", job_id)
            return

        await process_samples(session, job_id, samples, fetched_at=now)


def _job_tick(job_id: uuid.UUID) -> None:
    """Sync wrapper invoked by APScheduler."""
    try:
        _run_async(_execute_job(job_id))
    except Exception:
        logger.exception("Error in scheduled tick for job %s", job_id)


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
    logger.info("Scheduled job %s every %ds", job.id, job.interval_seconds)


def remove_scheduler_job(job_id: uuid.UUID) -> None:
    scheduler = _get_scheduler()
    sid = str(job_id)
    if scheduler.get_job(sid):
        scheduler.remove_job(sid)
        logger.info("Removed scheduler job %s", job_id)


def start_scheduler() -> None:
    global _loop
    _loop = asyncio.get_event_loop()
    scheduler = _get_scheduler()

    async def _load_jobs():
        async with async_session() as session:
            result = await session.execute(select(Job).where(Job.enabled == True))  # noqa: E712
            jobs = result.scalars().all()
            for job in jobs:
                add_scheduler_job(job)
            logger.info("Loaded %d jobs into scheduler", len(jobs))

    _loop.run_until_complete(_load_jobs())
    scheduler.start()


def stop_scheduler() -> None:
    scheduler = _get_scheduler()
    if scheduler.running:
        scheduler.shutdown(wait=False)
