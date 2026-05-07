import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.config import get_settings
from backend.utils.logger import setup_logging, get_logger
from backend.db.client import init_pool, close_pool, get_pool
from backend.db.migrations import run_migrations

setup_logging()
logger = get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("sqlmind_starting")
    await init_pool()
    await run_migrations()
    logger.info("sqlmind_ready", port=settings.port)
    yield
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


# ── Health ─────────────────────────────────────────────────────────────────


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


# ── Schema preview ─────────────────────────────────────────────────────────


@app.get("/api/schema")
async def get_schema_preview():
    from backend.agent.tools.get_schema import get_schema

    try:
        result = await get_schema({})
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Sync query ─────────────────────────────────────────────────────────────


class QueryRequest(BaseModel):
    question: str


@app.post("/api/query")
async def query(request: QueryRequest):
    """
    Synchronous endpoint — waits for full result then returns.
    Good for testing. Frontend uses /api/query/stream instead.
    """
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    from backend.agent.orchestrator import SQLMindAgent

    agent = SQLMindAgent(question=request.question)

    try:
        result = await agent.run()
        return result
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── SSE streaming query ────────────────────────────────────────────────────


@app.get("/api/query/stream")
async def query_stream(question: str):
    """
    SSE streaming endpoint — emits events as agent progresses.

    Why StreamingResponse + async generator?
    HTTP normally buffers the full response before sending.
    StreamingResponse tells FastAPI to send each chunk immediately as it's yielded.
    The browser's EventSource reads these chunks as they arrive.
    Format: each event is "data: {json}\n\n" — the double newline is the SSE spec.
    """
    if not question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    from backend.agent.orchestrator import SQLMindAgent

    async def event_generator():
        agent = SQLMindAgent(question=question)
        try:
            async for event in agent.run_streaming():
                # SSE format: "data: <json>\n\n"
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable Nginx buffering if behind proxy
        },
    )
