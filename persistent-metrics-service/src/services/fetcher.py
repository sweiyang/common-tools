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


async def fetch_instant(
    prometheus_url: str,
    query: str,
    timeout: float = 30.0,
) -> list[Sample]:
    """Call Prometheus /api/v1/query (instant) and return parsed samples."""
    url = f"{prometheus_url.rstrip('/')}/api/v1/query"
    params = {"query": query}

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
        labels = dict(sorted(metric.items()))

        value_pair = result.get("value")
        if value_pair is None:
            continue
        ts_epoch, val_str = value_pair
        samples.append(
            Sample(
                metric_name=metric_name,
                labels=labels,
                value=float(val_str),
                timestamp=datetime.fromtimestamp(float(ts_epoch), tz=timezone.utc),
            )
        )

    logger.info("Fetched %d samples for query=%s", len(samples), query)
    return samples
