from __future__ import annotations

import uuid

from apscheduler.triggers.cron import CronTrigger
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.auth import verify_api_key
from src.core.db import get_db
from src.core.db.db_models import Job
from src.schemas.job import JobCreate, JobResponse, JobTestResult, JobUpdate
from src.services.scheduler import add_scheduler_job, fetch_job_samples, remove_scheduler_job

router = APIRouter(
    prefix="/jobs",
    tags=["jobs"],
    dependencies=[Depends(verify_api_key)],
)


@router.post("/", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def create_job(body: JobCreate, db: Session = Depends(get_db)):
    job = Job(**body.model_dump())
    db.add(job)
    db.commit()
    db.refresh(job)
    add_scheduler_job(job)
    return job


@router.get("/", response_model=list[JobResponse])
async def list_jobs(
    enabled: bool | None = Query(default=None),
    db: Session = Depends(get_db),
):
    stmt = select(Job)
    if enabled is not None:
        stmt = stmt.where(Job.enabled == enabled)
    result = db.execute(stmt)
    return result.scalars().all()


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: uuid.UUID, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.patch("/{job_id}", response_model=JobResponse)
async def update_job(
    job_id: uuid.UUID,
    body: JobUpdate,
    db: Session = Depends(get_db),
):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    updates = body.model_dump(exclude_unset=True)

    # Handle schedule switching: setting cron clears interval and vice versa
    if "cron_expression" in updates and updates["cron_expression"] is not None:
        # Validate cron syntax
        try:
            CronTrigger.from_crontab(updates["cron_expression"])
        except ValueError as e:
            raise HTTPException(status_code=422, detail=f"Invalid cron expression: {e}")
        # Clear interval_seconds when switching to cron
        updates["interval_seconds"] = 0

    if "interval_seconds" in updates and updates["interval_seconds"] is not None and updates["interval_seconds"] > 0:
        # Clear cron when switching to interval
        updates["cron_expression"] = None

    for key, value in updates.items():
        setattr(job, key, value)

    # Validate combined state: must have exactly one schedule type
    has_cron = bool(job.cron_expression)
    has_interval = job.interval_seconds > 0
    if not has_cron and not has_interval:
        raise HTTPException(
            status_code=422,
            detail="Job must have either interval_seconds or cron_expression set",
        )

    # Validate source_type + query combination
    if job.source_type == "prometheus" and not job.query:
        raise HTTPException(
            status_code=422,
            detail="query is required when source_type is 'prometheus'",
        )

    db.commit()
    db.refresh(job)

    remove_scheduler_job(job_id)
    if job.enabled:
        add_scheduler_job(job)

    return job


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(job_id: uuid.UUID, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    remove_scheduler_job(job_id)
    db.delete(job)
    db.commit()


@router.post("/test", response_model=JobTestResult)
async def test_job(body: JobCreate):
    """Dry-run: fetch samples and simulate counter processing without persisting anything."""
    errors: list[str] = []
    raw_samples: list[dict] = []
    counter_states: list[dict] = []

    try:
        samples = fetch_job_samples(
            prometheus_url=body.prometheus_url,
            query=body.query,
            source_type=body.source_type,
            offset_seconds=body.offset_seconds,
        )
    except Exception as e:
        return JobTestResult(
            samples_fetched=0,
            samples=[],
            counter_states=[],
            errors=[str(e)],
        )

    for s in samples:
        raw_samples.append({
            "metric_name": s.metric_name,
            "labels": s.labels,
            "value": s.value,
            "timestamp": s.timestamp.isoformat(),
        })

    # Simulate counter processing in-memory (no prior state)
    state_map: dict[tuple, dict] = {}
    for s in samples:
        key = (s.metric_name, tuple(sorted(s.labels.items())))
        if key not in state_map:
            state_map[key] = {
                "metric_name": s.metric_name,
                "labels": s.labels,
                "last_raw_value": s.value,
                "checkpoint": 0.0,
                "accumulated_value": s.value,
            }
        else:
            state = state_map[key]
            if s.value < state["last_raw_value"]:
                state["checkpoint"] += state["last_raw_value"]
            state["last_raw_value"] = s.value
            state["accumulated_value"] = state["checkpoint"] + s.value

    counter_states = list(state_map.values())

    return JobTestResult(
        samples_fetched=len(samples),
        samples=raw_samples,
        counter_states=counter_states,
        errors=errors,
    )
