from __future__ import annotations

import json
import uuid

from apscheduler.triggers.cron import CronTrigger
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.auth import verify_api_key
from src.core.db import get_db
from src.core.db.db_models import CounterState, Job
from src.schemas.job import BaseValueEntry, BaseValueResponse, JobCreate, JobResponse, JobTestResult, JobUpdate
from src.services.conflict_checker import check_metric_conflicts
from src.services.scheduler import add_scheduler_job, fetch_job_samples, remove_scheduler_job

router = APIRouter(
    prefix="/jobs",
    tags=["jobs"],
    dependencies=[Depends(verify_api_key)],
)


@router.post("/", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def create_job(body: JobCreate, db: Session = Depends(get_db)):
    # Fetch samples and check for metric conflicts before persisting
    try:
        samples = fetch_job_samples(
            url=body.url,
            query=body.query,
            source_type=body.source_type,
            offset_seconds=body.offset_seconds,
        )
    except Exception:
        samples = []

    if samples:
        conflicts = check_metric_conflicts(db, samples)
        if conflicts:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "Job would produce metrics that conflict with existing jobs",
                    "conflicts": conflicts,
                },
            )

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

    # Check for metric conflicts if fetch-affecting fields changed
    fetch_fields_changed = {"url", "query", "source_type"} & updates.keys()
    if fetch_fields_changed:
        try:
            samples = fetch_job_samples(
                url=job.url,
                query=job.query,
                source_type=job.source_type,
                offset_seconds=job.offset_seconds,
            )
        except Exception:
            samples = []

        if samples:
            conflicts = check_metric_conflicts(db, samples, exclude_job_id=job_id)
            if conflicts:
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "message": "Updated job would produce metrics that conflict with existing jobs",
                        "conflicts": conflicts,
                    },
                )

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


@router.patch("/{job_id}/base-values", response_model=BaseValueResponse)
async def set_base_values(
    job_id: uuid.UUID,
    entries: list[BaseValueEntry],
    db: Session = Depends(get_db),
):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    updated = 0
    not_found: list[dict] = []

    for entry in entries:
        canonical = json.dumps(entry.labels, sort_keys=True, separators=(",", ":"))
        stmt = select(CounterState).where(
            CounterState.job_id == job_id,
            CounterState.metric_name == entry.metric_name,
            CounterState.labels == canonical,
        )
        state = db.execute(stmt).scalar_one_or_none()
        if state is not None:
            state.base_value = entry.base_value
            updated += 1
        else:
            not_found.append({"metric_name": entry.metric_name, "labels": entry.labels})

    db.commit()
    return BaseValueResponse(updated=updated, not_found=not_found)


@router.post("/test", response_model=JobTestResult)
async def test_job(body: JobCreate, db: Session = Depends(get_db)):
    """Dry-run: fetch samples and simulate counter processing without persisting anything."""
    errors: list[str] = []
    raw_samples: list[dict] = []
    counter_states: list[dict] = []

    try:
        samples = fetch_job_samples(
            url=body.url,
            query=body.query,
            source_type=body.source_type,
            offset_seconds=body.offset_seconds,
        )
    except Exception as e:
        return JobTestResult(
            samples_fetched=0,
            samples=[],
            counter_states=[],
            conflicts=[],
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
                "current_value": s.value,
                "checkpoint": 0.0,
                "count": s.value,
            }
        else:
            state = state_map[key]
            if s.value < state["current_value"]:
                state["checkpoint"] = state["count"]
            state["current_value"] = s.value
            state["count"] = state["checkpoint"] + s.value

    counter_states = list(state_map.values())

    # Check for conflicts (dry-run: report but don't block)
    conflicts = check_metric_conflicts(db, samples)

    return JobTestResult(
        samples_fetched=len(samples),
        samples=raw_samples,
        counter_states=counter_states,
        conflicts=conflicts,
        errors=errors,
    )
