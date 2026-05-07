from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import get_settings
from backend.utils.logger import setup_logging, get_logger
from backend.db.client import init_pool, close_pool, get_pool
from backend.db.migrations import run_migrations

setup_logging()
logger = get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("sqlmind_starting")
    await init_pool()
    await run_migrations()
    logger.info("sqlmind_ready", port=settings.port)
    yield
    # Shutdown
    await close_pool()
    logger.info("sqlmind_stopped")


app = FastAPI(
    title="SQLMind",
    description="Natural Language to SQL Agent",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        db_status = "connected"
    except Exception as e:
        logger.error("health_check_failed", error=str(e))
        db_status = "disconnected"

    return {
        "status": "ok",
        "db": db_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
