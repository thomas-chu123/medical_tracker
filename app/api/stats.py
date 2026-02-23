from datetime import date, datetime
from pydantic import BaseModel
from fastapi import APIRouter, Depends, status
import asyncio

from app.database import get_supabase
from app.auth import get_current_user
from app.scheduler import run_tracked_appointments

router = APIRouter(prefix="/api/stats", tags=["Stats"])

class GlobalStats(BaseModel):
    hospitals: int
    departments: int
    doctors: int
    snapshots_today: int
    notifications_today: int

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
    
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    notif_res = (
        supabase.table("notification_logs")
        .select("count", count="exact")
        .gte("sent_at", today_start)
        .limit(1)
        .execute()
    )
    
    return GlobalStats(
        hospitals=hosp_res.count or 0,
        departments=dept_res.count or 0,
        doctors=doc_res.count or 0,
        snapshots_today=snap_res.count or 0,
        notifications_today=notif_res.count or 0,
    )

@router.post("/scrape-now", status_code=status.HTTP_202_ACCEPTED)
async def trigger_scrape_now(current_user: dict = Depends(get_current_user)):
    asyncio.create_task(run_tracked_appointments())
    return {"message": "Scrape task triggered"}


class CrowdAnalysisResult(BaseModel):
    labels: list[str]
    data: list[float]

class DeptStats(BaseModel):
    dept_name: str
    avg_registered: float
    max_registered: int

class DoctorStats(BaseModel):
    doctor_name: str
    avg_registered: float

class DeptRankingItem(BaseModel):
    hospital_name: str
    dept_name: str
    category: str | None = None
    max_registered: int
    avg_registered: float

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

@router.get("/dept-comparison", response_model=CrowdAnalysisResult)
async def get_dept_comparison(hospital_id: str = None, category: str = None):
    """
    Returns average registered counts grouped by department.
    """
    supabase = get_supabase()
    
    query = supabase.table("appointment_snapshots").select("department_id, current_registered, departments!inner(name, hospital_id, category)")
    if hospital_id:
        query = query.eq("departments.hospital_id", hospital_id)
    if category:
        query = query.eq("departments.category", category)

    res = query.order("scraped_at", desc=True).limit(5000).execute()
    snapshots = res.data or []
    
    dept_data = {} # dept_id -> {sum, count, name}
    
    for s in snapshots:
        did = s.get("department_id")
        val = s.get("current_registered")
        dinfo = s.get("departments")
        dname = dinfo.get("name") if dinfo else "未知科室"
        
        if did and val is not None:
            if did not in dept_data:
                dept_data[did] = {"sum": 0, "count": 0, "name": dname}
            dept_data[did]["sum"] += val
            dept_data[did]["count"] += 1
            
    # Sort and format
    sorted_depts = sorted(dept_data.values(), key=lambda x: x["sum"]/x["count"], reverse=True)
    
    return CrowdAnalysisResult(
        labels=[x["name"] for x in sorted_depts[:15]], # Top 15 depts
        data=[round(x["sum"]/x["count"], 1) for x in sorted_depts[:15]]
    )

@router.get("/doctor-comparison", response_model=CrowdAnalysisResult)
async def get_doctor_comparison(hospital_id: str = None, dept_id: str = None, category: str = None):
    """
    Returns average registered counts for doctors.
    """
    supabase = get_supabase()
    
    query = supabase.table("appointment_snapshots").select("doctor_id, current_registered, doctors(name), departments!inner(category)")
    
    if dept_id:
        query = query.eq("department_id", dept_id)
    if hospital_id:
        query = query.eq("departments.hospital_id", hospital_id)
    if category:
        query = query.eq("departments.category", category)

    res = query.order("scraped_at", desc=True).limit(2000).execute()
    
    snapshots = res.data or []
    doc_data = {} # doc_id -> {sum, count, name}
    
    for s in snapshots:
        did = s.get("doctor_id")
        val = s.get("current_registered")
        dinfo = s.get("doctors")
        dname = dinfo.get("name") if dinfo else "未知醫師"
        
        if did and val is not None:
            if did not in doc_data:
                doc_data[did] = {"sum": 0, "count": 0, "name": dname}
            doc_data[did]["sum"] += val
            doc_data[did]["count"] += 1
            
    # Format
    return CrowdAnalysisResult(
        labels=[x["name"] for x in doc_data.values()],
        data=[round(x["sum"]/x["count"], 1) for x in doc_data.values()]
    )

@router.get("/dept-ranking", response_model=list[DeptRankingItem])
async def get_dept_ranking():
    """
    Returns detailed department ranking.
    """
    supabase = get_supabase()
    
    # Fetch snapshots with joined hospital and department info
    res = (
        supabase.table("appointment_snapshots")
        .select("department_id, current_registered, departments(name, hospital_id, hospitals(name))")
        .order("scraped_at", desc=True)
        .limit(5000)
        .execute()
    )
    
    snapshots = res.data or []
    groups = {} # dept_id -> {sum, count, max, dept_name, hosp_name}
    
    for s in snapshots:
        val = s.get("current_registered")
        d_id = s.get("department_id")
        d_info = s.get("departments") or {}
        h_info = d_info.get("hospitals") or {}
        
        if d_id and val is not None:
            if d_id not in groups:
                groups[d_id] = {
                    "sum": 0, 
                    "count": 0, 
                    "max": 0, 
                    "dept_name": d_info.get("name", "未知"), 
                    "hosp_name": h_info.get("name", "未知")
                }
            groups[d_id]["sum"] += val
            groups[d_id]["count"] += 1
            groups[d_id]["max"] = max(groups[d_id]["max"], val)
            
    ranking = []
    for g in groups.values():
        ranking.append(DeptRankingItem(
            hospital_name=g["hosp_name"],
            dept_name=g["dept_name"],
            category=g.get("category"),
            max_registered=g["max"],
            avg_registered=round(g["sum"] / g["count"], 1)
        ))
        
    return sorted(ranking, key=lambda x: x.avg_registered, reverse=True)


@router.get("/doctor-speed", response_model=CrowdAnalysisResult)
async def get_doctor_speed(hospital_id: str = None, category: str = None, dept_id: str = None):
    """
    Returns speed (avg patients / 4 hours) for doctors.
    """
    supabase = get_supabase()
    
    query = supabase.table("appointment_snapshots").select("doctor_id, current_registered, doctors(name), departments!inner(hospital_id, category)")
    
    if hospital_id:
        query = query.eq("departments.hospital_id", hospital_id)
    if category:
        query = query.eq("departments.category", category)
    if dept_id:
        query = query.eq("department_id", dept_id)
        
    res = query.order("scraped_at", desc=True).limit(3000).execute()
    snapshots = res.data or []
    
    doc_data = {} # doc_id -> {sum, count, name}
    for s in snapshots:
        did = s.get("doctor_id")
        val = s.get("current_registered")
        dinfo = s.get("doctors")
        dname = dinfo.get("name") if dinfo else "未知醫師"
        
        if did and val is not None:
            if did not in doc_data:
                doc_data[did] = {"sum": 0, "count": 0, "name": dname}
            doc_data[did]["sum"] += val
            doc_data[did]["count"] += 1
            
    # Calculate speed: average / 4 hours
    results = []
    for d in doc_data.values():
        avg = d["sum"] / d["count"]
        speed = round(avg / 4, 2)
        results.append({"name": d["name"], "speed": speed})
        
    results = sorted(results, key=lambda x: x["speed"], reverse=True)[:20] # Top 20 speedsters
    
    return CrowdAnalysisResult(
        labels=[x["name"] for x in results],
        data=[x["speed"] for x in results]
    )

@router.get("/categories")
async def get_categories():
    """
    Returns unique department categories.
    """
    supabase = get_supabase()
    res = supabase.table("departments").select("category").execute()
    cats = sorted(list(set(d["category"] for d in res.data if d.get("category"))))
    return cats
