from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from careloop.api import calls, dashboard, patients
from careloop.config import settings
from careloop.db import init_db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    scheduler = None
    if settings.scheduler_enabled:
        from careloop.scheduler import start_scheduler

        scheduler = start_scheduler()
    yield
    if scheduler:
        scheduler.shutdown(wait=False)
    await calls.close_webrtc()


app = FastAPI(title="CareLoop", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(dashboard.router)
app.include_router(patients.router)
app.include_router(calls.router)


@app.get("/api/health")
def health():
    return {"ok": True, "voice_enabled": settings.voice_enabled, "llm_enabled": settings.llm_enabled}
