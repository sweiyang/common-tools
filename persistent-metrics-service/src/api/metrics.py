from __future__ import annotations

import json
import re

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.db import get_db
from src.core.db.db_models import CounterState, Job

router = APIRouter(tags=["metrics"])


def _to_snake_case(name: str) -> str:
    """Convert camelCase/PascalCase to snake_case and replace hyphens with underscores."""
    # Insert underscore before uppercase letters that follow a lowercase letter or digit
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    # Insert underscore between consecutive uppercase followed by lowercase (e.g. HTTPServer -> HTTP_Server)
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", s)
    return s.lower().replace("-", "_")


def _render_prometheus(rows: list[tuple[CounterState, str]]) -> str:
    """Render counter states into Prometheus text exposition format."""
    lines: list[str] = []
    current_metric: str | None = None

    for state, app_name in rows:
        full_metric_name = _to_snake_case(f"{app_name}_{state.metric_name}")
        if full_metric_name != current_metric:
            current_metric = full_metric_name
            lines.append(f"# HELP {full_metric_name} {full_metric_name}")
            lines.append(f"# TYPE {full_metric_name} counter")

        labels = json.loads(state.labels) if state.labels else {}
        label_pairs = ",".join(
            f'{k}="{v}"' for k, v in sorted(labels.items())
        )
        label_str = f"{{{label_pairs}}}" if label_pairs else ""
        value = state.base_value + state.count
        ts_ms = int(state.updated_at.timestamp() * 1000)
        lines.append(f"{full_metric_name}{label_str} {value} {ts_ms}")

    lines.append("")
    return "\n".join(lines)


@router.get(
    "/metrics",
    response_class=PlainTextResponse,
    summary="Prometheus metrics endpoint",
)
async def get_metrics(db: Session = Depends(get_db)):
    stmt = (
        select(CounterState, Job.application_name)
        .join(Job, CounterState.job_id == Job.id)
        .order_by(Job.application_name, CounterState.metric_name)
    )
    result = db.execute(stmt)
    rows = result.all()
    body = _render_prometheus(rows)
    return PlainTextResponse(
        content=body,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
