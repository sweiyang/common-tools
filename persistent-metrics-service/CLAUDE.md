# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Service Does

A FastAPI relay that makes Prometheus counter metrics durable. It polls Prometheus on a schedule (via registered "jobs"), detects counter resets, accumulates values, persists them in YugabyteDB, and re-exposes them at `GET /metrics` for external Prometheus scraping. Counter values survive restarts of both the original source systems and this service.

## Commands

**Setup:**
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config.yaml.example config.yaml  # then edit api_key and DB settings
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
4. `metrics_repository.py` (`process_samples`) detects counter resets and updates `counter_states`
5. `GET /metrics` reads `counter_states` and returns `checkpoint + last_raw_value` per series in Prometheus text format (type `counter`)

**Key design points:**
- Counter reset detection: if the new raw value < the previous raw value, the checkpoint is advanced by the previous raw value, and accumulation continues seamlessly
- `counter_states` stores one row per (job, metric_name, labels) with `current_value` and `checkpoint`
- Labels are stored as JSONB with a GIN index for flexible querying
- All DB operations are **sync** (psycopg2 driver, sync SQLAlchemy sessions)
- The `Database` class (`src/core/db/db.py`) handles schema creation, search_path, column sync, and table creation
- `/metrics` is unauthenticated; all `/jobs/*` endpoints require `X-API-Key` header
- DB tables are created on startup via `db.sync_schema()` + `db.create_tables()`
- Logging uses loguru via `src/core/logging.py` (`setup_logging()` / `get_logger()`)

## Configuration

Config is loaded from `config.yaml` (path overridable via `CONFIG_PATH` env var). Environment-aware DB config via `APP_ENV` env var (defaults to `"prod"`):

```yaml
database:
  prod:
    host: "localhost"
    port: 5433
    dbname: "yugabyte"
    user: "yugabyte"
    credential: "yugabyte"
    schema: "metrics"
auth:
  api_key: "your-secret-key"
server:
  host: "0.0.0.0"
  port: 8000
logging:
  level: "INFO"
  format: "{time:YYYY-MM-DD HH:mm:ss} - {extra[name]} - {level} - {message}"
```

YugabyteDB is PostgreSQL-compatible (YSQL). The psycopg2 driver is used throughout.
