# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Service Does

A FastAPI relay that makes Prometheus counter metrics durable. It polls Prometheus on a schedule (via registered "jobs"), detects counter resets, accumulates values, persists them in YugabyteDB, and re-exposes them at `GET /metrics` for external Prometheus scraping. Counter values survive restarts of both the original source systems and this service.

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
3. `fetcher.py` runs an instant query (`/api/v1/query`) against Prometheus
4. `metrics_repository.py` (`process_samples`) detects counter resets, updates `counter_states`, and appends a `counter_samples` row with the accumulated value
5. `GET /metrics` reads `counter_states` and returns `checkpoint + last_raw_value` per series in Prometheus text format (type `counter`)

**Key design points:**
- Counter reset detection: if the new raw value < the previous raw value, the checkpoint is advanced by the previous raw value, and accumulation continues seamlessly
- `counter_states` stores one row per (job, metric_name, labels) with `last_raw_value` and `checkpoint`; `counter_samples` is the append-only history
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
