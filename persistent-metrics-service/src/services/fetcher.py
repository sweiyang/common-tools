from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)


@dataclass
class Sample:
    metric_name: str
    labels: dict
    value: float
    timestamp: datetime


async def fetch_range(
    prometheus_url: str,
    query: str,
    start: datetime,
    end: datetime,
    step: str = "15s",
    timeout: float = 30.0,
) -> list[Sample]:
    """Call Prometheus /api/v1/query_range and return parsed samples."""
    url = f"{prometheus_url.rstrip('/')}/api/v1/query_range"
    params = {
        "query": query,
        "start": start.timestamp(),
        "end": end.timestamp(),
        "step": step,
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()

    body = resp.json()
    if body.get("status") != "success":
        logger.error("Prometheus query failed: %s", body.get("error", "unknown"))
        return []

    samples: list[Sample] = []
    for result in body.get("data", {}).get("result", []):
        metric = result.get("metric", {})
        metric_name = metric.pop("__name__", "unknown")
        labels = metric  # remaining keys are labels

        for ts_val in result.get("values", []):
            ts_epoch, val_str = ts_val
            samples.append(
                Sample(
                    metric_name=metric_name,
                    labels=dict(sorted(labels.items())),
                    value=float(val_str),
                    timestamp=datetime.fromtimestamp(float(ts_epoch), tz=timezone.utc),
                )
            )

    logger.info("Fetched %d samples for query=%s", len(samples), query)
    return samples
