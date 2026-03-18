# Persistent Metrics Service

A FastAPI service that queries Prometheus servers on a schedule, detects counter resets, accumulates durable counter values in YugabyteDB, and re-exposes them via a `/metrics` endpoint for persistent Prometheus scraping.

## Quick start

### 1. Start the full demo stack

```bash
# Start YugabyteDB, Prometheus, and an example metrics app
docker-compose up -d

# Verify all services are running
docker-compose ps
```

Services:
- **YugabyteDB**: `localhost:5433`
- **Prometheus**: `http://localhost:9090` (scraping the example app)
- **Example App**: `http://localhost:8080/metrics` (generates sample metrics)

### 2. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure

```bash
cp config.yaml.example config.yaml
# Edit config.yaml with your API key (DB URL works with docker-compose defaults)
```

### 4. Run

```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

The API docs are at `http://localhost:8000/docs`.

### 5. Register a job to persist example-app metrics

```bash
curl -X POST http://localhost:8000/jobs/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: change-me-to-a-real-secret" \
  -d '{
    "name": "Example HTTP requests",
    "prometheus_url": "http://localhost:9090",
    "query": "example_http_requests_total",
    "interval_seconds": 30
  }'
```

See **[docs/USER_GUIDE.md](docs/USER_GUIDE.md)** for detailed job onboarding instructions.

## Usage

### Register a job

```bash
curl -X POST http://localhost:8000/jobs/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "name": "cpu metrics",
    "prometheus_url": "http://prometheus:9090",
    "query": "node_cpu_seconds_total",
    "interval_seconds": 300
  }'
```

### List jobs

```bash
curl http://localhost:8000/jobs/ -H "X-API-Key: your-api-key"
```

### Scrape persistent metrics

```bash
curl http://localhost:8000/metrics
```

Point your external Prometheus at `http://<this-service>:8000/metrics` as a scrape target.

## Configuration

All configuration lives in `config.yaml`:

```yaml
database:
  url: "postgresql+asyncpg://yugabyte:yugabyte@localhost:5433/yugabyte"

auth:
  api_key: "your-secret-key"

server:
  host: "0.0.0.0"
  port: 8000
```

You can override the config file path with the `CONFIG_PATH` environment variable.

## Example App

The `example-app/` directory contains a sample Python application that generates realistic Prometheus metrics. This service is designed for **counter metrics only**. Relevant example-app counters:

- `example_http_requests_total` — Counter with method, endpoint, status labels
- `example_orders_processed_total` — Counter with region and product labels

The example app also exports gauges and histograms (`example_active_connections`, `example_request_latency_seconds`, `example_queue_size`), but this service only tracks counters with reset detection.

Run it standalone:
```bash
cd example-app
pip install prometheus-client
python app.py
# Metrics at http://localhost:8080/metrics
```

Or via docker-compose (included in `docker-compose up`).

## Documentation

- **[docs/USER_GUIDE.md](docs/USER_GUIDE.md)** — Step-by-step guide to onboarding jobs
- **[docs/prd.md](docs/prd.md)** — Product requirements document

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Your App       │────▶│  Prometheus     │────▶│  Persistent     │
│  (exports       │     │  (scrapes &     │     │  Metrics Svc    │
│   /metrics)     │     │   stores temp)  │     │  (queries API)  │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                                                         ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  External       │◀────│  GET /metrics   │◀────│  YugabyteDB     │
│  Prometheus     │     │  (latest values)│     │  (durable)      │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```
