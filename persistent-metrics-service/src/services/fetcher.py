from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from prometheus_client.parser import text_string_to_metric_families

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
    query_time: float | None = None,
) -> list[Sample]:
    """Call Prometheus /api/v1/query (instant) and return parsed samples."""
    url = f"{prometheus_url.rstrip('/')}/api/v1/query"
    params: dict = {"query": query}
    if query_time is not None:
        params["time"] = query_time

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


def fetch_metrics_endpoint(
    target_url: str,
    metric_filter: str | None = None,
    timeout: float = 30.0,
) -> list[Sample]:
    """Fetch and parse a Prometheus text exposition /metrics endpoint directly.

    Only counter-type metrics are returned (this service's data model is counter-specific).
    If metric_filter is provided, only metrics matching that name are included.
    """
    with httpx.Client(timeout=timeout) as client:
        resp = client.get(target_url)
        resp.raise_for_status()

    now = datetime.now(timezone.utc)
    text_data = resp.text
    samples: list[Sample] = []

    for family in text_string_to_metric_families(text_data):
        # Only collect counter metrics
        if family.type != "counter":
            continue

        if metric_filter and family.name != metric_filter:
            continue

        for sample in family.samples:
            # prometheus_client parser may append _total or _created suffixes
            # We only want the base counter value (with _total suffix)
            if sample.name.endswith("_created"):
                continue

            labels = dict(sorted(sample.labels.items()))
            samples.append(
                Sample(
                    metric_name=sample.name,
                    labels=labels,
                    value=float(sample.value),
                    timestamp=now,
                )
            )

    logger.info(
        "Fetched {} counter samples from {} (filter={})",
        len(samples), target_url, metric_filter,
    )
    return samples
