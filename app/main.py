"""
Main FastAPI application entry point.
"""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import auth, users, hospitals, tracking, stats, admin, webhooks
from app.scheduler import start_scheduler, stop_scheduler
from app.config import get_settings
from app.auth import seed_super_user
from app.core.logger import logger

STATIC_DIR = Path(__file__).parent.parent / "static"

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("🚀 Medical Appointment Tracker starting...")
    await seed_super_user()
    start_scheduler()
    yield
    # Shutdown
    stop_scheduler()
    logger.info("👋 Medical Appointment Tracker stopped.")


app = FastAPI(
    title="台灣醫療門診追蹤系統",
    description=(
        "自動蒐集台灣各大醫院門診掛號資料，"
        "並在門診進度接近時以 Email / LINE 通知使用者。"
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS - adjust origins for production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(hospitals.router)
app.include_router(tracking.router)
app.include_router(stats.router)
app.include_router(admin.router)
app.include_router(webhooks.router)  # LINE Message API webhook

# Serve static files (CSS, JS)
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def serve_frontend():
    """Serve the SPA dashboard."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "ok",
        "service": "台灣醫療門診追蹤系統",
        "version": "1.0.0",
    }


@app.post("/api/admin/scrape-now", tags=["Admin"])
async def trigger_scrape_now():
    """Manually trigger an appointment scrape cycle (for testing)."""
    from app.scheduler import run_tracked_appointments
    asyncio.create_task(run_tracked_appointments())
    return {"message": "Scrape task queued"}


@app.post("/api/admin/master-data-now", tags=["Admin"])
async def trigger_master_data_now():
    """Manually trigger a master data scrape (departments + doctors)."""
    from app.scheduler import run_cmuh_master_data
    asyncio.create_task(run_cmuh_master_data())
    return {"message": "Master data scrape task queued"}

