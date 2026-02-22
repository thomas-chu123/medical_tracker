import os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.auth import get_current_user
from app.scheduler import get_scheduler
from app.database import get_supabase
from app.models.tracking import AdminTrackingOut

router = APIRouter(prefix="/api/admin", tags=["Admin"])
LOG_FILE = Path(__file__).parent.parent.parent / "server.log"


def require_super_admin(current_user: dict = Depends(get_current_user)):
    """Middleware to verify admin rights. Currently assumes logged in = admin."""
    # In a real app, check current_user["role"] == "admin"
    pass


@router.get("/tracking", response_model=list[AdminTrackingOut])
async def list_all_tracking(admin=Depends(require_super_admin)):
    """Get all tracking subscriptions across the system."""
    supabase = get_supabase()
    
    # Fetch all subscriptions
    result = supabase.table("tracking_subscriptions").select("*").order("created_at", desc=True).execute()
    subs = result.data
    if not subs:
        return []

    # Batch fetch users
    user_ids = list({s["user_id"] for s in subs if s.get("user_id")})
    users_map = {}
    if user_ids:
        users = supabase.table("users").select("id, email, display_name").in_("id", user_ids).execute()
        users_map = {u["id"]: u for u in users.data}

    # Batch fetch doctors
    doctor_ids = list({s["doctor_id"] for s in subs if s.get("doctor_id")})
    doctors_map = {}
    if doctor_ids:
        docs = supabase.table("doctors").select("id, name, specialty, hospital_id, department_id").in_("id", doctor_ids).execute()
        doctors_map = {d["id"]: d for d in docs.data}
        
    # Batch fetch departments
    dept_ids_set = {s["department_id"] for s in subs if s.get("department_id")}
    for d in doctors_map.values():
        if d.get("department_id"):
            dept_ids_set.add(d["department_id"])
    
    dept_ids = list(dept_ids_set)
    depts_map = {}
    if dept_ids:
        depts = supabase.table("departments").select("id, name, category").in_("id", dept_ids).execute()
        depts_map = {d["id"]: d for d in depts.data}

    # Batch fetch hospitals
    hospital_ids = list({d.get("hospital_id") for d in doctors_map.values() if d.get("hospital_id")})
    hospitals_map = {}
    if hospital_ids:
        hosps = supabase.table("hospitals").select("id, name").in_("id", hospital_ids).execute()
        hospitals_map = {h["id"]: h["name"] for h in hosps.data}

    # Enrich
    enriched = []
    for s in subs:
        user = users_map.get(s.get("user_id"), {})
        doc = doctors_map.get(s.get("doctor_id"), {})
        
        d_id = s.get("department_id") or doc.get("department_id")
        dept = depts_map.get(d_id, {})
        
        hosp_name = hospitals_map.get(doc.get("hospital_id"), "")
        
        s["user_email"] = user.get("email")
        s["user_name"] = user.get("display_name")
        s["doctor_name"] = doc.get("name", "")
        s["department_name"] = dept.get("name") or "（未知科室）"
        s["hospital_name"] = hosp_name or "（未知醫院）"
        enriched.append(s)

    return enriched


@router.delete("/tracking/{sub_id}")
async def delete_tracking(sub_id: str, admin=Depends(require_super_admin)):
    """Delete a tracking subscription."""
    supabase = get_supabase()
    res = supabase.table("tracking_subscriptions").delete().eq("id", sub_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="找不到該追蹤紀錄")
    return {"message": "追蹤紀錄已刪除"}


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
