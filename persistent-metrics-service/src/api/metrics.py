from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.models.counter_state import CounterState

router = APIRouter(tags=["metrics"])


def _render_prometheus(rows: list[CounterState]) -> str:
    """Render counter states into Prometheus text exposition format."""
    lines: list[str] = []
    current_metric: str | None = None

    for state in rows:
        if state.metric_name != current_metric:
            current_metric = state.metric_name
            lines.append(f"# TYPE {state.metric_name} counter")

        label_pairs = ",".join(
            f'{k}="{v}"' for k, v in sorted(state.labels.items())
        )
        label_str = f"{{{label_pairs}}}" if label_pairs else ""
        value = state.checkpoint + state.last_raw_value
        ts_ms = int(state.updated_at.timestamp() * 1000)
        lines.append(f"{state.metric_name}{label_str} {value} {ts_ms}")

    lines.append("")
    return "\n".join(lines)


@router.get(
    "/metrics",
    response_class=PlainTextResponse,
    summary="Prometheus metrics endpoint",
)
async def get_metrics(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(CounterState).order_by(CounterState.metric_name)
    )
    rows = result.scalars().all()
    body = _render_prometheus(rows)
    return PlainTextResponse(
        content=body,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
