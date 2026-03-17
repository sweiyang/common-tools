"""
Example application that exposes Prometheus metrics.

This simulates a real service with:
- Request counters (by endpoint and status)
- Active connections gauge
- Request latency histogram
- A custom business metric (orders processed)

Metrics change over time to demonstrate realistic scraping.
"""

import random
import threading
import time

from prometheus_client import Counter, Gauge, Histogram, start_http_server

# Metrics definitions
REQUEST_COUNT = Counter(
    "example_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)

ACTIVE_CONNECTIONS = Gauge(
    "example_active_connections",
    "Number of active connections",
)

REQUEST_LATENCY = Histogram(
    "example_request_latency_seconds",
    "Request latency in seconds",
    ["endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

ORDERS_PROCESSED = Counter(
    "example_orders_processed_total",
    "Total orders processed",
    ["region", "product_type"],
)

QUEUE_SIZE = Gauge(
    "example_queue_size",
    "Current size of the processing queue",
    ["queue_name"],
)


def simulate_traffic():
    """Simulate realistic application traffic."""
    endpoints = ["/api/users", "/api/orders", "/api/products", "/health"]
    methods = ["GET", "POST", "PUT", "DELETE"]
    statuses = ["200", "201", "400", "404", "500"]
    status_weights = [70, 10, 8, 7, 5]  # 200 most common

    regions = ["us-east", "us-west", "eu-west", "ap-south"]
    products = ["electronics", "clothing", "food", "software"]

    while True:
        # Simulate HTTP requests
        endpoint = random.choice(endpoints)
        method = random.choice(methods)
        status = random.choices(statuses, weights=status_weights)[0]
        REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=status).inc()

        # Simulate latency
        latency = random.expovariate(10)  # ~100ms average
        REQUEST_LATENCY.labels(endpoint=endpoint).observe(latency)

        # Update active connections (fluctuates between 10-100)
        connections = random.randint(10, 100)
        ACTIVE_CONNECTIONS.set(connections)

        # Simulate order processing
        if random.random() < 0.3:  # 30% chance per tick
            region = random.choice(regions)
            product = random.choice(products)
            ORDERS_PROCESSED.labels(region=region, product_type=product).inc()

        # Update queue sizes
        for queue in ["orders", "notifications", "analytics"]:
            size = random.randint(0, 50)
            QUEUE_SIZE.labels(queue_name=queue).set(size)

        # Sleep 0.5-2 seconds between updates
        time.sleep(random.uniform(0.5, 2.0))


def main():
    print("Starting example metrics app on :8080")
    start_http_server(9999)

    # Start traffic simulation in background
    traffic_thread = threading.Thread(target=simulate_traffic, daemon=True)
    traffic_thread.start()

    # Keep main thread alive
    while True:
        time.sleep(60)


if __name__ == "__main__":
    main()
