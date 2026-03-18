from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.auth import verify_api_key
from src.core.db import get_db
from src.core.db.db_models import Job
from src.schemas.job import JobCreate, JobResponse, JobUpdate
from src.services.scheduler import add_scheduler_job, remove_scheduler_job

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
    for key, value in updates.items():
        setattr(job, key, value)

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
