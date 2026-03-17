from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class JobCreate(BaseModel):
    name: str | None = None
    prometheus_url: str = Field(..., examples=["http://prometheus:9090"])
    query: str = Field(..., examples=["node_cpu_seconds_total"])
    interval_seconds: int = Field(..., gt=0, examples=[300])
    step: str = Field(default="15s", examples=["15s"])


class JobUpdate(BaseModel):
    name: str | None = None
    prometheus_url: str | None = None
    query: str | None = None
    interval_seconds: int | None = Field(default=None, gt=0)
    step: str | None = None
    enabled: bool | None = None


class JobResponse(BaseModel):
    id: uuid.UUID
    name: str | None
    prometheus_url: str
    query: str
    interval_seconds: int
    step: str
    enabled: bool
    last_queried_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
