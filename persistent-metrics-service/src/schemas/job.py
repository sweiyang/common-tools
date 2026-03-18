from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class JobCreate(BaseModel):
    name: str | None = None
    prometheus_url: str = Field(..., examples=["http://prometheus:9090"])
    query: str = Field(..., examples=["example_http_requests_total"])
    interval_seconds: int = Field(..., gt=0, examples=[300])


class JobUpdate(BaseModel):
    name: str | None = None
    prometheus_url: str | None = None
    query: str | None = None
    interval_seconds: int | None = Field(default=None, gt=0)
    enabled: bool | None = None


class JobResponse(BaseModel):
    id: uuid.UUID
    name: str | None
    prometheus_url: str
    query: str
    interval_seconds: int
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
