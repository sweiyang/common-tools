from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.db import get_db
from src.core.db.db_models import CounterState

router = APIRouter(tags=["metrics"])


def _render_prometheus(rows: list[CounterState]) -> str:
    """Render counter states into Prometheus text exposition format."""
    lines: list[str] = []
    current_metric: str | None = None

    for state in rows:
        if state.metric_name != current_metric:
            current_metric = state.metric_name
            lines.append(f"# TYPE {state.metric_name} counter")

        labels = json.loads(state.labels) if state.labels else {}
        label_pairs = ",".join(
            f'{k}="{v}"' for k, v in sorted(labels.items())
        )
        label_str = f"{{{label_pairs}}}" if label_pairs else ""
        value = state.base_value + state.count
        ts_ms = int(state.updated_at.timestamp() * 1000)
        lines.append(f"{state.metric_name}{label_str} {value} {ts_ms}")

    lines.append("")
    return "\n".join(lines)


@router.get(
    "/metrics",
    response_class=PlainTextResponse,
    summary="Prometheus metrics endpoint",
)
async def get_metrics(db: Session = Depends(get_db)):
    result = db.execute(
        select(CounterState).order_by(CounterState.metric_name)
    )
    rows = result.scalars().all()
    body = _render_prometheus(rows)
    return PlainTextResponse(
        content=body,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
