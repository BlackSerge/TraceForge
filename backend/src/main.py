from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy import update

from src.db.session import SessionLocal
from src.models.run import AgentRun, RunStatus
from src.routers import agent, evals, traces

@asynccontextmanager
async def lifespan(_: FastAPI):
    """Reaper: this is the only process running agents, so at startup any pending/running run lost its
    process. Without this it would stay in progress forever (and the UI would keep polling it)."""
    async with SessionLocal() as session:
        await session.execute(
            update(AgentRun)
            .where(AgentRun.status.in_([RunStatus.PENDING, RunStatus.RUNNING]))
            .values(status=RunStatus.FAILED, finished_at=datetime.now(timezone.utc),
                    rejection_reason="Orphaned: process ended before the run finished")
        )
        await session.commit()
    yield


app = FastAPI(title="DevPilot Agent", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)

app.include_router(agent.router)
app.include_router(traces.router)
app.include_router(evals.router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "devpilot-agent"}