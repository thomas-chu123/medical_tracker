import os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.auth import get_current_user
from app.scheduler import get_scheduler

router = APIRouter(prefix="/api/admin", tags=["Admin"])
LOG_FILE = Path(__file__).parent.parent.parent / "server.log"


class LogResponse(BaseModel):
    content: str
    size_bytes: int
    last_modified: str


class JobStatus(BaseModel):
    id: str
    name: str
    next_run_time: str | None


class SchedulerStatus(BaseModel):
    is_running: bool
    jobs: list[JobStatus]


def require_super_admin(current_user: dict = Depends(get_current_user)):
    """Middleware to verify admin rights. Currently assumes logged in = admin."""
    # In a real app, check current_user["role"] == "admin"
    pass


@router.get("/scheduler", response_model=SchedulerStatus)
async def get_scheduler_status(admin=Depends(require_super_admin)):
    """Get current running background tasks."""
    scheduler = get_scheduler()
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None
        })
    return {
        "is_running": scheduler.running,
        "jobs": jobs
    }


@router.post("/scheduler/pause")
async def pause_scheduler(admin=Depends(require_super_admin)):
    """Pause all background schedule tasks."""
    scheduler = get_scheduler()
    if scheduler.running:
        scheduler.pause()
    return {"message": "Scheduler paused"}


@router.post("/scheduler/resume")
async def resume_scheduler(admin=Depends(require_super_admin)):
    """Resume all background schedule tasks."""
    scheduler = get_scheduler()
    if scheduler.running:
        scheduler.resume()
    return {"message": "Scheduler resumed"}


@router.get("/logs", response_model=LogResponse)
async def read_logs(lines: int = 100, admin=Depends(require_super_admin)):
    """Read the last N lines of the server.log file."""
    if not LOG_FILE.exists():
        return {"content": "No log file found.", "size_bytes": 0, "last_modified": ""}
    
    try:
        stat = LOG_FILE.stat()
        # Simple tail implementation
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            content_lines = f.readlines()
            
        return {
            "content": "".join(content_lines[-lines:]),
            "size_bytes": stat.st_size,
            "last_modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/logs")
async def clear_logs(admin=Depends(require_super_admin)):
    """Clear the server.log file."""
    if LOG_FILE.exists():
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.truncate(0)
    return {"message": "Logs cleared"}

@router.post("/scrape-now", status_code=status.HTTP_202_ACCEPTED)
async def trigger_scrape_now(admin=Depends(require_super_admin)):
    """Trigger background scraping immediately."""
    import asyncio
    from app.scheduler import run_cmuh_appointments
    asyncio.create_task(run_cmuh_appointments())
    return {"message": "Scrape task triggered"}
