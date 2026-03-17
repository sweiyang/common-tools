# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Service Does

A FastAPI relay that makes Prometheus metrics durable. It polls Prometheus on a schedule (via registered "jobs"), persists samples in YugabyteDB, and re-exposes them at `GET /metrics` for external Prometheus scraping. Metrics survive restarts of the original source systems.

## Commands

**Setup:**
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config.yaml.example config.yaml  # then edit api_key and DB URL
```

**Run the service:**
```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

**Start infrastructure (YugabyteDB on 5433, Prometheus on 9090, example-app on 8080):**
```bash
docker-compose up -d
```

There are no automated tests in this repo.

## Architecture

```
Source App → Prometheus → [this service polls via jobs] → YugabyteDB → GET /metrics → External Prometheus
```

**Request flow for metric collection:**
1. User registers a job (`POST /jobs`) with a Prometheus URL, PromQL query, and interval
2. `scheduler.py` (APScheduler `BackgroundScheduler` in a thread) fires the job on its interval
3. `fetcher.py` calls Prometheus `/api/v1/query_range` from `last_queried_at` to now
4. `metrics_repository.py` bulk-inserts samples with `ON CONFLICT DO NOTHING` dedup
5. `GET /metrics` uses `DISTINCT ON (metric_name, labels)` to return the latest value per label set in Prometheus text format

**Key design points:**
- `last_queried_at` on the Job model enables incremental fetching — only new samples are fetched each run
- Labels are stored as JSONB with a GIN index for flexible querying
- The scheduler bridges sync APScheduler → async coroutines via `asyncio.run()` in `_run_async()`
- `/metrics` is unauthenticated; all `/jobs/*` endpoints require `X-API-Key` header
- DB tables are created on startup via SQLAlchemy `create_all` (no migrations)

## Configuration

Config is loaded from `config.yaml` (path overridable via `CONFIG_PATH` env var):

```yaml
database:
  url: "postgresql+asyncpg://yugabyte:yugabyte@localhost:5433/yugabyte"
auth:
  api_key: "your-secret-key"
server:
  host: "0.0.0.0"
  port: 8000
```

YugabyteDB is PostgreSQL-compatible (YSQL). The asyncpg driver is used throughout.
