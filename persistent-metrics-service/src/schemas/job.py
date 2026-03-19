from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from apscheduler.triggers.cron import CronTrigger
from pydantic import BaseModel, Field, model_validator


class JobCreate(BaseModel):
    name: str | None = None
    prometheus_url: str = Field(..., examples=["http://prometheus:9090"])
    query: str | None = Field(default=None, examples=["example_http_requests_total"])
    interval_seconds: int | None = Field(default=None, gt=0, examples=[300])
    offset_seconds: int = Field(default=0, ge=0, examples=[900])
    cron_expression: str | None = Field(default=None, examples=["*/5 * * * *"])
    source_type: Literal["prometheus", "metrics_endpoint"] = "prometheus"

    @model_validator(mode="after")
    def validate_schedule_and_source(self) -> JobCreate:
        # Exactly one of interval_seconds or cron_expression must be set
        has_interval = self.interval_seconds is not None
        has_cron = self.cron_expression is not None

        if not has_interval and not has_cron:
            raise ValueError("Either interval_seconds or cron_expression must be provided")
        if has_interval and has_cron:
            raise ValueError("Cannot set both interval_seconds and cron_expression")

        # Validate cron syntax
        if has_cron:
            try:
                CronTrigger.from_crontab(self.cron_expression)
            except ValueError as e:
                raise ValueError(f"Invalid cron expression: {e}") from e
            # Sentinel: store 0 for interval_seconds when cron is used
            self.interval_seconds = 0

        # Source type validation
        if self.source_type == "prometheus" and not self.query:
            raise ValueError("query is required when source_type is 'prometheus'")

        # When metrics_endpoint and query is None, store empty string for DB NOT NULL
        if self.source_type == "metrics_endpoint" and self.query is None:
            self.query = ""

        return self


class JobUpdate(BaseModel):
    name: str | None = None
    prometheus_url: str | None = None
    query: str | None = None
    interval_seconds: int | None = Field(default=None, gt=0)
    offset_seconds: int | None = Field(default=None, ge=0)
    cron_expression: str | None = None
    source_type: Literal["prometheus", "metrics_endpoint"] | None = None
    enabled: bool | None = None


class JobResponse(BaseModel):
    id: uuid.UUID
    name: str | None
    prometheus_url: str
    query: str
    interval_seconds: int
    offset_seconds: int
    cron_expression: str | None
    source_type: str
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class JobTestResult(BaseModel):
    samples_fetched: int
    samples: list[dict]
    counter_states: list[dict]
    errors: list[str]
