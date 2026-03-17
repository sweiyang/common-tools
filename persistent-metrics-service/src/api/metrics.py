from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db

router = APIRouter(tags=["metrics"])

_LATEST_SQL = """
SELECT DISTINCT ON (metric_name, labels)
       metric_name, labels, value, timestamp
FROM   metric_samples
ORDER  BY metric_name, labels, timestamp DESC;
"""


def _render_prometheus(rows) -> str:
    """Render rows into Prometheus text exposition format."""
    lines: list[str] = []
    current_metric: str | None = None

    for metric_name, labels, value, ts in rows:
        if metric_name != current_metric:
            current_metric = metric_name
            lines.append(f"# TYPE {metric_name} gauge")

        label_pairs = ",".join(
            f'{k}="{v}"' for k, v in sorted(labels.items())
        )
        label_str = f"{{{label_pairs}}}" if label_pairs else ""
        ts_ms = int(ts.timestamp() * 1000)
        lines.append(f"{metric_name}{label_str} {value} {ts_ms}")

    lines.append("")
    return "\n".join(lines)


@router.get(
    "/metrics",
    response_class=PlainTextResponse,
    summary="Prometheus metrics endpoint",
)
async def get_metrics(db: AsyncSession = Depends(get_db)):
    result = await db.execute(text(_LATEST_SQL))
    rows = result.fetchall()
    body = _render_prometheus(rows)
    return PlainTextResponse(
        content=body,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
