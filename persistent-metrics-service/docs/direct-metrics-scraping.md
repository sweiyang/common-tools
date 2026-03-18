# Direct `/metrics` Endpoint Scraping — Implementation Workflow

## Motivation

Today the service only supports polling via the **Prometheus query API** (`/api/v1/query` instant queries). This requires a running Prometheus instance between the source application and this service:

```
Source App /metrics  →  Prometheus  →  This Service (instant query)  →  YugabyteDB
```

Adding direct `/metrics` scraping removes the Prometheus middleman for use cases where users simply want to persist raw exporter output:

```
Source App /metrics  →  This Service (direct scrape)  →  YugabyteDB
```

This is useful when:
- The source application exposes a `/metrics` endpoint but there is no Prometheus server in the environment.
- Users want to reduce infrastructure complexity (no Prometheus needed just for persistence).
- Metrics need to be captured from short-lived or ephemeral targets that Prometheus may miss.

---

## Current Architecture (for context)

### Job model (`src/models/job.py`)
A job currently stores:
- `prometheus_url` — base URL of the Prometheus server
- `query` — a PromQL expression
- `interval_seconds` — poll frequency

### Fetch path (`src/services/fetcher.py`)
`fetch_instant()` calls `{prometheus_url}/api/v1/query` (instant query), parses the JSON response into `Sample` dataclasses (`metric_name`, `labels`, `value`, `timestamp`).

### Processing path (`src/services/metrics_repository.py`)
`process_samples()` performs counter reset detection per series: if the new raw value < previous raw value, the checkpoint is advanced. It updates `counter_states` (one row per series) and appends to `counter_samples` (append-only history with accumulated values).

### Scheduler (`src/services/scheduler.py`)
APScheduler `BackgroundScheduler` fires `_job_tick()` → `_execute_job()` on each job's interval. The async coroutine is run in the scheduler thread via `asyncio.run_until_complete()`.

---

## Implementation Plan

### Phase 1: Job Model Changes

**File:** `src/models/job.py`

Add a `source_type` field to distinguish between job modes:

| Field | Type | Values | Default |
|-------|------|--------|---------|
| `source_type` | `String(32)` | `"prometheus_api"`, `"metrics_endpoint"` | `"prometheus_api"` |

For `metrics_endpoint` jobs:
- `prometheus_url` is repurposed as the target URL (e.g., `http://my-app:8080/metrics`). Consider renaming to `target_url` or adding it as an alias.
- `query` becomes optional (not used for direct scraping, or could be used as a filter pattern).
- `step` is not applicable.

**Migration note:** Existing jobs default to `source_type="prometheus_api"` — fully backward compatible, no migration needed since the service uses `create_all`.

### Phase 2: Prometheus Text Exposition Parser

**New file:** `src/services/metrics_parser.py`

Write a parser for the [Prometheus text exposition format](https://prometheus.io/docs/instrumenting/exposition_formats/#text-based-format). The parser needs to handle:

1. **Comment lines** — `# HELP`, `# TYPE`, and plain `#` comments
2. **Metric lines** — `metric_name{label1="val1",label2="val2"} value [timestamp]`
3. **Metrics without labels** — `metric_name value [timestamp]`
4. **Metric types** — counter, gauge, histogram, summary, untyped

Output: list of the existing `Sample` dataclass from `fetcher.py`:
```python
@dataclass
class Sample:
    metric_name: str
    labels: dict
    value: float
    timestamp: datetime
```

Key considerations:
- If the exposition line includes a timestamp, use it. If not, use "now" (time of scrape).
- Labels should be sorted by key (consistent with existing `fetch_instant` behavior).
- Consider using an existing library like [`prometheus_client.parser`](https://github.com/prometheus/client_python) which provides `text_string_to_metric_families()` — this avoids writing a parser from scratch and handles edge cases (escaped quotes in labels, multi-line help strings, etc.).

### Phase 3: Direct Scrape Fetcher

**File:** `src/services/fetcher.py`

Add a new async function alongside the existing `fetch_instant()`:

```python
async def fetch_metrics_endpoint(
    target_url: str,
    timeout: float = 30.0,
) -> list[Sample]:
    """Scrape a Prometheus /metrics endpoint and return parsed samples."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(target_url)
        resp.raise_for_status()

    return parse_prometheus_text(resp.text)
```

The function:
1. GETs the target URL
2. Passes the response body to the text exposition parser
3. Returns the same `list[Sample]` that `fetch_instant` returns

Because both functions return `list[Sample]`, the downstream processing path (`process_samples`) needs **zero changes**.

### Phase 4: Scheduler Dispatch

**File:** `src/services/scheduler.py`

Update `_execute_job()` to branch on `job.source_type`:

```python
async def _execute_job(job_id: uuid.UUID) -> None:
    async with async_session() as session:
        job = await session.get(Job, job_id)
        if job is None or not job.enabled:
            return

        now = datetime.now(timezone.utc)

        try:
            if job.source_type == "metrics_endpoint":
                samples = await fetch_metrics_endpoint(
                    target_url=job.prometheus_url,
                )
            else:
                samples = await fetch_instant(
                    prometheus_url=job.prometheus_url,
                    query=job.query,
                )
        except Exception:
            logger.exception("Fetch failed for job %s", job_id)
            return

        await process_samples(session, job_id, samples, fetched_at=now)
```

**Important:** For `metrics_endpoint` jobs, the same `process_samples()` path handles reset detection and accumulation. Both job types share the same downstream processing.

### Phase 5: Schema / API Changes

**File:** `src/schemas/job.py`

Update `JobCreate` and `JobResponse`:

```python
class JobCreate(BaseModel):
    name: str | None = None
    source_type: str = Field(default="prometheus_api", pattern="^(prometheus_api|metrics_endpoint)$")
    prometheus_url: str  # acts as target_url for metrics_endpoint jobs
    query: str | None = Field(default=None)  # required only for prometheus_api
    interval_seconds: int = Field(..., gt=0)
```

Add validation: if `source_type == "prometheus_api"`, then `query` is required. This can be done with a Pydantic `model_validator`.

**File:** `src/api/jobs.py`

No structural changes needed — the existing CRUD endpoints work as-is since they pass through all fields.

### Phase 6: Dedup Behavior for Direct Scraping

The existing dedup constraint on `counter_samples` is `(job_id, metric_name, labels, timestamp)`. For `metrics_endpoint` jobs this means:

- If the target's `/metrics` does **not** include timestamps (common for gauges/counters), the parser assigns "now" as the timestamp. Each scrape gets a different timestamp → **no dedup collisions** → every scrape inserts new rows. This is the correct behavior — it captures the metric value at each point in time.

- If the target **does** include timestamps and the value hasn't changed, the same `(job_id, metric_name, labels, timestamp)` tuple is seen again → `ON CONFLICT DO NOTHING` kicks in → no duplicates. Also correct.

No changes needed to the dedup logic.

---

## File Change Summary

| File | Change |
|------|--------|
| `src/models/job.py` | Add `source_type` column |
| `src/schemas/job.py` | Add `source_type` field, make `query` optional with validation |
| `src/services/metrics_parser.py` | **New** — Prometheus text format parser (or wrap `prometheus_client.parser`) |
| `src/services/fetcher.py` | Add `fetch_metrics_endpoint()` function |
| `src/services/scheduler.py` | Branch `_execute_job()` on `source_type` |
| `src/api/jobs.py` | No changes (pass-through) |
| `src/api/metrics.py` | No changes (reads from `counter_states` table) |
| `src/services/metrics_repository.py` | No changes (same `Sample` → same `process_samples` path) |
| `requirements.txt` | Potentially add `prometheus_client` if using its parser |

---

## Example Usage

### Register a direct scrape job

```bash
curl -X POST http://localhost:8000/jobs/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: change-me-to-a-real-secret" \
  -d '{
    "name": "My app metrics",
    "source_type": "metrics_endpoint",
    "prometheus_url": "http://my-app:8080/metrics",
    "interval_seconds": 30
  }'
```

### Existing Prometheus API jobs still work identically

```bash
curl -X POST http://localhost:8000/jobs/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: change-me-to-a-real-secret" \
  -d '{
    "name": "HTTP requests via PromQL",
    "source_type": "prometheus_api",
    "prometheus_url": "http://localhost:9090",
    "query": "example_http_requests_total",
    "interval_seconds": 60
  }'
```

---

## Open Questions

1. **Field naming:** Should `prometheus_url` be renamed to `target_url` (breaking change) or should a new `target_url` field be added alongside it? A third option is to keep `prometheus_url` as-is and document that it serves as the target URL for `metrics_endpoint` jobs.

2. **Filtering:** Should `metrics_endpoint` jobs support an optional filter (e.g., regex on metric names) to avoid persisting every metric from a noisy exporter?

3. **Authentication to targets:** Some `/metrics` endpoints require auth (Bearer token, basic auth). Should the job model support optional `auth_header` or `basic_auth` fields?

4. **Content negotiation:** Some exporters support OpenMetrics format (`application/openmetrics-text`) in addition to the classic text format. Should the parser handle both, or only the classic format initially?

5. **Health checking:** For `metrics_endpoint` jobs, should there be a health/reachability check at job creation time (a quick HEAD or GET to validate the URL)?
