from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from src.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class Sample:
    metric_name: str
    labels: dict
    value: float
    timestamp: datetime


def fetch_instant(
    prometheus_url: str,
    query: str,
    timeout: float = 30.0,
) -> list[Sample]:
    """Call Prometheus /api/v1/query (instant) and return parsed samples."""
    url = f"{prometheus_url.rstrip('/')}/api/v1/query"
    params = {"query": query}

    with httpx.Client(timeout=timeout) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()

    body = resp.json()
    if body.get("status") != "success":
        logger.error("Prometheus query failed: {}", body.get("error", "unknown"))
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

    logger.info("Fetched {} samples for query={}", len(samples), query)
    return samples
