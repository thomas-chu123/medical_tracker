from datetime import date, datetime
from pydantic import BaseModel
from fastapi import APIRouter, Depends, status
import asyncio

from app.database import get_supabase
from app.auth import get_current_user
from app.scheduler import run_tracked_appointments
from app.core.timezone import today_tw_str, now_utc_str
from app.core.logger import logger

router = APIRouter(prefix="/api/stats", tags=["Stats"])

# In-memory cache for dashboard statistics
# Structure: { "global": { hospital_id: GlobalStats }, "crowd": { hospital_id: CrowdAnalysisResult } }
_STATS_CACHE = {
    "global": {},
    "crowd": {}
}


class GlobalStats(BaseModel):
    hospitals: int
    departments: int
    doctors: int
    snapshots_today: int
    notifications_today: int

async def calculate_global_stats(hospital_id: str = None) -> GlobalStats:
    """Heavy computation logic for global statistics."""
    supabase = get_supabase()
    
    # 1. Hospitals count
    if hospital_id:
        hosp_res = supabase.table("hospitals").select("count", count="exact").eq("id", hospital_id).limit(1).execute()
    else:
        hosp_res = supabase.table("hospitals").select("count", count="exact").limit(1).execute()
        
    # 2. Departments count
    dept_query = supabase.table("departments").select("count", count="exact")
    if hospital_id:
        dept_query = dept_query.eq("hospital_id", hospital_id)
    dept_res = dept_query.limit(1).execute()
    
    # 3. Doctors count
    doc_query = supabase.table("doctors").select("count", count="exact")
    if hospital_id:
        doc_query = doc_query.eq("hospital_id", hospital_id)
    doc_res = doc_query.limit(1).execute()
    
    # 4. Snapshots & 5. Notifications
    today_tw = today_tw_str()
    class Dummy: count = 0

    if hospital_id:
        doc_ids_res = supabase.table("doctors").select("id").eq("hospital_id", hospital_id).execute()
        doc_ids = [d["id"] for d in doc_ids_res.data]
        
        if doc_ids:
            batch_size = 100
            total_snap_count = 0
            for i in range(0, len(doc_ids), batch_size):
                batch = doc_ids[i:i + batch_size]
                res = (
                    supabase.table("appointment_snapshots")
                    .select("count", count="exact")
                    .eq("session_date", today_tw)
                    .in_("doctor_id", batch)
                    .limit(1)
                    .execute()
                )
                total_snap_count += res.count or 0
            snap_count = total_snap_count
            
            sub_ids = []
            for i in range(0, len(doc_ids), batch_size):
                batch = doc_ids[i:i + batch_size]
                res = supabase.table("tracking_subscriptions").select("id").in_("doctor_id", batch).execute()
                sub_ids.extend([s["id"] for s in res.data])
            
            if sub_ids:
                total_notif_count = 0
                for i in range(0, len(sub_ids), batch_size):
                    batch = sub_ids[i:i + batch_size]
                    res = (
                        supabase.table("notification_logs")
                        .select("count", count="exact")
                        .gte("sent_at", f"{today_tw}T00:00:00Z")
                        .in_("subscription_id", batch)
                        .limit(1)
                        .execute()
                    )
                    total_notif_count += res.count or 0
                notif_count = total_notif_count
            else:
                notif_count = 0
        else:
            snap_count = 0
            notif_count = 0
    else:
        snap_res = supabase.table("appointment_snapshots").select("count", count="exact").eq("session_date", today_tw).limit(1).execute()
        snap_count = snap_res.count or 0
        notif_res = supabase.table("notification_logs").select("count", count="exact").gte("sent_at", f"{today_tw}T00:00:00Z").limit(1).execute()
        notif_count = notif_res.count or 0
    
    return GlobalStats(
        hospitals=hosp_res.count or 0,
        departments=dept_res.count or 0,
        doctors=doc_res.count or 0,
        snapshots_today=snap_count,
        notifications_today=notif_count,
    )

@router.get("/global", response_model=GlobalStats)
async def get_global_stats(hospital_id: str = None):
    cache_key = hospital_id or "all"
    if cache_key in _STATS_CACHE["global"]:
        return _STATS_CACHE["global"][cache_key]
    
    # Fallback/First time
    stats_data = await calculate_global_stats(hospital_id)
    _STATS_CACHE["global"][cache_key] = stats_data
    return stats_data


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

async def calculate_crowd_analysis(hospital_id: str = None) -> CrowdAnalysisResult:
    """Heavy computation logic for crowd analysis charts."""
    supabase = get_supabase()
    
    snapshots = []
    if hospital_id:
        doc_ids_res = supabase.table("doctors").select("id").eq("hospital_id", hospital_id).execute()
        doc_ids = [d["id"] for d in doc_ids_res.data]
        if not doc_ids:
            return CrowdAnalysisResult(labels=["上午", "下午", "晚上"], data=[0, 0, 0])
            
        batch_size = 100
        for i in range(0, len(doc_ids), batch_size):
            batch = doc_ids[i:i + batch_size]
            res = (
                supabase.table("appointment_snapshots")
                .select("session_type, current_registered")
                .in_("doctor_id", batch)
                .order("scraped_at", desc=True)
                .limit(2000)
                .execute()
            )
            snapshots.extend(res.data or [])
    else:
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
            
    averages = {}
    for stype in group_totals.keys():
        if group_counts[stype] > 0:
            averages[stype] = round(group_totals[stype] / group_counts[stype], 1)
        else:
            averages[stype] = 0.0
            
    return CrowdAnalysisResult(
        labels=list(averages.keys()),
        data=list(averages.values())
    )

@router.get("/crowd-analysis", response_model=CrowdAnalysisResult)
async def get_crowd_analysis(hospital_id: str = None):
    cache_key = hospital_id or "all"
    if cache_key in _STATS_CACHE["crowd"]:
        return _STATS_CACHE["crowd"][cache_key]
        
    crowd_data = await calculate_crowd_analysis(hospital_id)
    _STATS_CACHE["crowd"][cache_key] = crowd_data
    return crowd_data


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
        
        # Robustly handle joined doctor info
        dinfo = s.get("doctors")
        if isinstance(dinfo, list) and len(dinfo) > 0:
            dinfo = dinfo[0]
        elif not isinstance(dinfo, dict):
            dinfo = {}
            
        dname = dinfo.get("name") if dinfo else "未知醫師"
        
        if did and val is not None:
            if did not in doc_data:
                doc_data[did] = {"sum": 0, "count": 0, "name": dname}
            doc_data[did]["sum"] += val
            doc_data[did]["count"] += 1
            
    # Calculate speed: average / 4 hours
    results = []
    for d in doc_data.values():
        if d["count"] == 0: continue
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

# Background Cache Refresher
async def refresh_stats_cache_task():
    """Periodically refreshes the global and crowd statistics cache."""
    await asyncio.sleep(5) # Give some time for app startup
    while True:
        try:
            logger.info("🔄 Refreshing dashboard stats cache...")
            supabase = get_supabase()
            
            # 1. Get all hospitals
            hospitals_res = supabase.table("hospitals").select("id").execute()
            hosp_ids = [h["id"] for h in hospitals_res.data]
            
            # 2. Add 'None' for 'All Hospitals'
            target_hids = [None] + hosp_ids
            
            for hid in target_hids:
                cache_key = hid or "all"
                
                # Global Stats
                g_stats = await calculate_global_stats(hid)
                _STATS_CACHE["global"][cache_key] = g_stats
                
                # Crowd Analysis
                c_stats = await calculate_crowd_analysis(hid)
                _STATS_CACHE["crowd"][cache_key] = c_stats
                
                # Small sleep to be nice to DB during background refresh
                await asyncio.sleep(0.5)
                
            logger.info(f"✅ Dashboard stats cache refreshed for {len(target_hids)} targets.")
            
        except Exception as e:
            logger.error(f"❌ Error refreshing stats cache: {e}")
            
        # Refresh every hour
        await asyncio.sleep(3600)

def start_stats_refresher():
    """Initiates the background stats refresher task."""
    asyncio.create_task(refresh_stats_cache_task())

