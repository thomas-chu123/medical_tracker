from datetime import date
from pydantic import BaseModel
from fastapi import APIRouter
from app.database import get_supabase

router = APIRouter(prefix="/api/stats", tags=["Stats"])

class GlobalStats(BaseModel):
    hospitals: int
    departments: int
    doctors: int
    snapshots_today: int

@router.get("/global", response_model=GlobalStats)
async def get_global_stats():
    supabase = get_supabase()
    
    # Get counts
    hosp_res = supabase.table("hospitals").select("count", count="exact").limit(1).execute()
    dept_res = supabase.table("departments").select("count", count="exact").limit(1).execute()
    doc_res = supabase.table("doctors").select("count", count="exact").limit(1).execute()
    
    today = str(date.today())
    snap_res = (
        supabase.table("appointment_snapshots")
        .select("count", count="exact")
        .eq("session_date", today)
        .limit(1)
        .execute()
    )
    
    return GlobalStats(
        hospitals=hosp_res.count or 0,
        departments=dept_res.count or 0,
        doctors=doc_res.count or 0,
        snapshots_today=snap_res.count or 0,
    )


class CrowdAnalysisResult(BaseModel):
    labels: list[str]
    data: list[float]

@router.get("/crowd-analysis", response_model=CrowdAnalysisResult)
async def get_crowd_analysis():
    """
    Returns average crowd metrics (current_registered) grouped by session type 
    (Morning, Afternoon, Evening) for visualization.
    """
    supabase = get_supabase()
    
    # We fetch a sample of recent snapshots (e.g. up to 2000 records) to compute averages.
    # In a production environment with massive data, this should be done via a SQL View or RPC.
    res = (
        supabase.table("appointment_snapshots")
        .select("session_type, current_registered")
        .order("scraped_at", desc=True)
        .limit(2000)
        .execute()
    )
    
    snapshots = res.data or []
    
    group_totals = {"上午": 0, "下午": 0, "晚上": 0}
    group_counts = {"上午": 0, "下午": 0, "晚上": 0}
    
    for s in snapshots:
        val = s.get("current_registered")
        stype = s.get("session_type")
        
        if val is not None and stype in group_totals:
            group_totals[stype] += val
            group_counts[stype] += 1
            
    # Calculate averages
    averages = {}
    for stype in group_totals.keys():
        if group_counts[stype] > 0:
            averages[stype] = round(group_totals[stype] / group_counts[stype], 1)
        else:
            averages[stype] = 0.0
            
    # Format for Chart.js: labels and data parallel arrays
    return CrowdAnalysisResult(
        labels=list(averages.keys()),
        data=list(averages.values())
    )

