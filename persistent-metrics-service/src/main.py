from contextlib import asynccontextmanager

from src.core.logging import setup_logging, get_logger

setup_logging()
logger = get_logger(__name__)

from fastapi import FastAPI

from src.api.jobs import router as jobs_router
from src.api.metrics import router as metrics_router
from src.core.db import get_db_instance
from src.services.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = get_db_instance()
    db.sync_schema()
    db.create_tables()

    start_scheduler()
    logger.info("Scheduler started")

    yield

    stop_scheduler()
    logger.info("Scheduler stopped")

    db.engine.dispose()
    logger.info("Database engine disposed")


app = FastAPI(
    title="Persistent Metrics Service",
    description="Relay Prometheus metrics through YugabyteDB for persistence",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(jobs_router)
app.include_router(metrics_router)


@app.get("/health")
async def health():
    return {"status": "healthy"}
