# Persistent Metrics Service — PRD

## Problem

Prometheus metrics are ephemeral. When a target restarts, its counters reset. When Prometheus itself restarts or is replaced, historical scrape data can be lost. Operators need a way to persist metric data beyond the lifecycle of any single process.

## Solution

A FastAPI service that acts as a **persistent counter metrics relay** with reset detection:

1. Users register **jobs** via API — each job points at a source Prometheus server, a PromQL query, and a scrape interval.
2. A background scheduler periodically runs instant queries against the source Prometheus (`/api/v1/query`), detects counter resets, and accumulates durable counter values.
3. Counter states and samples are stored in **YugabyteDB** (PostgreSQL-compatible distributed SQL).
4. The service exposes a **`GET /metrics`** endpoint that renders the accumulated value per (metric_name, labels) in Prometheus text exposition format (type `counter`).
5. An external Prometheus can scrape this `/metrics` endpoint and see durable, persistent counter metrics that survive source restarts.

## Key decisions

- **Counter-only focus**: The service is designed specifically for counter metrics with built-in reset detection. When a source application restarts and its counters reset, the service detects the drop and continues accumulating seamlessly.
- **Source**: Prometheus HTTP query API (instant query), not raw exporter endpoints.
- **Storage**: YugabyteDB (YSQL) — chosen for distributed SQL durability and PostgreSQL compatibility.
- **Auth**: API-key based (`X-API-Key` header) on job management endpoints; `/metrics` is unauthenticated for Prometheus scraping.
- **Config**: `config.yaml` file (database URL, API key, server settings).

## API summary

- `POST /jobs` — register a new scrape job
- `GET /jobs` — list jobs
- `GET /jobs/{id}` — get a job
- `PATCH /jobs/{id}` — update a job
- `DELETE /jobs/{id}` — remove a job
- `GET /metrics` — Prometheus text exposition of latest stored values
