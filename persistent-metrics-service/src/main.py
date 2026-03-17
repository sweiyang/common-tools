import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.jobs import router as jobs_router
from src.api.metrics import router as metrics_router
from src.core.database import engine, Base
from src.services.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created")

    start_scheduler()
    logger.info("Scheduler started")

    yield

    stop_scheduler()
    logger.info("Scheduler stopped")

    await engine.dispose()
    logger.info("Database engine disposed")


app = FastAPI(
    title="Persistent Metrics Service",
    description="Relay Prometheus metrics through YugabyteDB for persistence",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(jobs_router)
app.include_router(metrics_router)
