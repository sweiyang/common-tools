# User Guide: Onboarding Jobs

This guide walks you through setting up the Persistent Metrics Service and registering jobs to scrape metrics from Prometheus.

## Prerequisites

- Docker and Docker Compose installed
- `curl` or similar HTTP client
- A Prometheus server with metrics you want to persist (or use the included example)

## Step 1: Start the Infrastructure

```bash
cd persistent-metrics-service

# Start YugabyteDB, Prometheus, and the example app
docker-compose up -d

# Verify everything is running
docker-compose ps
```

Services will be available at:
- **YugabyteDB**: `localhost:5433` (PostgreSQL-compatible)
- **Prometheus**: `http://localhost:9090` (with example-app metrics)
- **Example App**: `http://localhost:8080/metrics` (raw metrics)

## Step 2: Configure and Start the Service

```bash
# Create your config file
cp config.yaml.example config.yaml

# Edit config.yaml - set your API key
# The default database URL works with docker-compose

# Install dependencies
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Start the service
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

The service is now running at `http://localhost:8000`.

## Step 3: Register Your First Job

A job tells the service what to scrape from Prometheus. Here's the anatomy of a job:

| Field | Required | Description |
|-------|----------|-------------|
| `name` | No | Human-readable name for the job |
| `prometheus_url` | Yes | Base URL of the Prometheus server |
| `query` | Yes | PromQL expression to fetch (should return counter metrics) |
| `interval_seconds` | Yes | How often to fetch (in seconds) |

### Example: Scrape HTTP request metrics

```bash
curl -X POST http://localhost:8000/jobs/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: change-me-to-a-real-secret" \
  -d '{
    "name": "HTTP requests",
    "prometheus_url": "http://localhost:9090",
    "query": "example_http_requests_total",
    "interval_seconds": 60
  }'
```

Response:
```json
{
  "id": "a1b2c3d4-...",
  "name": "HTTP requests",
  "prometheus_url": "http://localhost:9090",
  "query": "example_http_requests_total",
  "interval_seconds": 60,
  "enabled": true,
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:00Z"
}
```

The job is now active. The service will:
1. Immediately schedule the job
2. Every 60 seconds, run an instant query against Prometheus, detect counter resets, and accumulate values
3. Store counter states and samples in YugabyteDB

## Step 4: Register More Jobs

### Scrape multiple counter metrics

> **Note:** This service is designed for **counter metrics only**. It uses reset detection and accumulation to produce durable counter values. Gauges and histograms are not supported.

```bash
# HTTP request counters
curl -X POST http://localhost:8000/jobs/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: change-me-to-a-real-secret" \
  -d '{
    "name": "HTTP requests",
    "prometheus_url": "http://localhost:9090",
    "query": "example_http_requests_total",
    "interval_seconds": 30
  }'

# Orders by region (using PromQL aggregation)
curl -X POST http://localhost:8000/jobs/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: change-me-to-a-real-secret" \
  -d '{
    "name": "Orders by region",
    "prometheus_url": "http://localhost:9090",
    "query": "sum by (region) (example_orders_processed_total)",
    "interval_seconds": 120
  }'
```

### Using PromQL expressions

The `query` field accepts any valid PromQL:

```bash
# Rate of requests over 5 minutes
"query": "rate(example_http_requests_total[5m])"

# Filter by label
"query": "example_http_requests_total{status=\"500\"}"

# Aggregation
"query": "sum by (endpoint) (example_http_requests_total)"

# Multiple metrics with regex
"query": "{__name__=~\"example_.*\"}"
```

## Step 5: View Persisted Metrics

Once jobs have run, metrics are stored in YugabyteDB and exposed via `/metrics`:

```bash
curl http://localhost:8000/metrics
```

Output (Prometheus text format):
```
# TYPE example_http_requests_total counter
example_http_requests_total{endpoint="/api/users",method="GET",status="200"} 1523 1705312200000
example_http_requests_total{endpoint="/api/orders",method="POST",status="201"} 342 1705312200000
# TYPE example_orders_processed_total counter
example_orders_processed_total{product="widgets",region="us-east"} 890 1705312200000
```

### Point external Prometheus at this endpoint

Add to your external Prometheus `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: "persistent-metrics"
    static_configs:
      - targets: ["your-service-host:8000"]
```

Now your external Prometheus scrapes **persistent, durable metrics** from YugabyteDB.

## Step 6: Manage Jobs

### List all jobs

```bash
curl http://localhost:8000/jobs/ \
  -H "X-API-Key: change-me-to-a-real-secret"
```

### List only enabled jobs

```bash
curl "http://localhost:8000/jobs/?enabled=true" \
  -H "X-API-Key: change-me-to-a-real-secret"
```

### Get a specific job

```bash
curl http://localhost:8000/jobs/{job_id} \
  -H "X-API-Key: change-me-to-a-real-secret"
```

### Update a job

```bash
# Change the interval
curl -X PATCH http://localhost:8000/jobs/{job_id} \
  -H "Content-Type: application/json" \
  -H "X-API-Key: change-me-to-a-real-secret" \
  -d '{"interval_seconds": 120}'

# Disable a job
curl -X PATCH http://localhost:8000/jobs/{job_id} \
  -H "Content-Type: application/json" \
  -H "X-API-Key: change-me-to-a-real-secret" \
  -d '{"enabled": false}'

# Change the query
curl -X PATCH http://localhost:8000/jobs/{job_id} \
  -H "Content-Type: application/json" \
  -H "X-API-Key: change-me-to-a-real-secret" \
  -d '{"query": "rate(example_http_requests_total[1m])"}'
```

### Delete a job

```bash
curl -X DELETE http://localhost:8000/jobs/{job_id} \
  -H "X-API-Key: change-me-to-a-real-secret"
```

Note: Deleting a job removes it from the scheduler but **keeps historical data** in `counter_states` in the database.

## Common Patterns

### Pattern 1: Persist critical business metrics

```bash
curl -X POST http://localhost:8000/jobs/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: change-me-to-a-real-secret" \
  -d '{
    "name": "Revenue metrics",
    "prometheus_url": "http://production-prometheus:9090",
    "query": "{__name__=~\"revenue_.*|orders_.*|payments_.*\"}",
    "interval_seconds": 60
  }'
```

### Pattern 2: Cross-cluster aggregation

Register jobs pointing at different Prometheus servers:

```bash
# Cluster A
curl -X POST http://localhost:8000/jobs/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: change-me-to-a-real-secret" \
  -d '{
    "name": "Cluster A requests",
    "prometheus_url": "http://prometheus-cluster-a:9090",
    "query": "sum(rate(http_requests_total[5m]))",
    "interval_seconds": 60
  }'

# Cluster B
curl -X POST http://localhost:8000/jobs/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: change-me-to-a-real-secret" \
  -d '{
    "name": "Cluster B requests",
    "prometheus_url": "http://prometheus-cluster-b:9090",
    "query": "sum(rate(http_requests_total[5m]))",
    "interval_seconds": 60
  }'
```

### Counter Reset Behavior

This service automatically handles counter resets. When a source application restarts and its counters reset to zero, the service detects the drop in raw value and advances an internal checkpoint. The accumulated value exposed via `/metrics` continues increasing seamlessly — no manual intervention required.

## Troubleshooting

### Job not fetching data

1. Check the job is enabled:
   ```bash
   curl http://localhost:8000/jobs/{job_id} -H "X-API-Key: ..."
   ```

2. Verify Prometheus is reachable from the service:
   ```bash
   curl "http://localhost:9090/api/v1/query?query=up"
   ```

3. Check service logs for errors:
   ```bash
   # If running with uvicorn directly
   # Logs appear in the terminal
   
   # Check for fetch errors in output
   ```

### No metrics on /metrics endpoint

1. Wait for at least one job interval to pass
2. Verify the job is enabled and check service logs for fetch/reset-detection activity
3. Check that the query returns data in Prometheus directly

### Authentication errors

Ensure you're passing the correct API key in the `X-API-Key` header. The key must match what's in your `config.yaml`.

## Architecture Recap

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

The key insight: even if the original Prometheus restarts or loses data, your metrics survive in YugabyteDB and remain accessible via `/metrics`.
