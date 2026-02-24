from fastapi import APIRouter, Query, HTTPException
from datetime import datetime, date, timedelta
from typing import Optional, List

from app.database import get_supabase
from app.models.hospital import HospitalOut, DepartmentOut, DoctorOut, SnapshotOut

router = APIRouter(prefix="/api", tags=["Hospitals"])

def calculate_eta(
    session_date_str: str,
    session_type: str, 
    current_number: Optional[int],
    registered_count: int, 
    waiting_list: list[int],
    target_number: Optional[int] = None
) -> Optional[str]:
    """
    Calculate Estimated Appointment Time (ETA).
    - If target_number is NOT provided: Returns the doctor's current estimated progress time.
    - If target_number IS provided: Returns the estimated time for that specific patient.
    
    Formula: Clinic Start Time + (People Ahead) * 5 minutes.
    """
    if not session_type or not session_date_str:
        return None
        
    start_times = {
        "上午": "08:30",
        "下午": "13:30",
        "晚上": "18:00"
    }
    start_time_str = start_times.get(session_type)
    if not start_time_str:
        return None
        
    try:
        # 1. Date and Time Context
        now = datetime.now()
        today = now.date()
        
        try:
            target_date = datetime.strptime(session_date_str, "%Y-%m-%d").date()
        except ValueError:
            return None

        # 2. Base Start Time Calculation
        schedule_start = datetime.combine(target_date, datetime.strptime(start_time_str, "%H:%M").time())
        
        if target_date < today:
            # Past clinic session
            return "已結束"

        # 3. Calculate how many people are ahead
        total_people_ahead = 0
        if target_number:
            if waiting_list:
                # Count people in waiting list whose number is strictly less than target
                total_people_ahead = len([x for x in waiting_list if x < target_number])
            elif current_number is not None:
                # Fallback: estimate based on current progress
                total_people_ahead = max(0, target_number - current_number)
            else:
                # Absolute fallback: from the start
                total_people_ahead = max(0, target_number - 1)
                
            # If target number is already passed and not in waiting list
            if current_number is not None and target_number < current_number:
                if not waiting_list or target_number not in waiting_list:
                    return "已過號"
        else:
            # Doctor's current time: Based on how many are already finished
            waiting_count = len(waiting_list) if waiting_list else 0
            total_people_ahead = (registered_count or 0) - waiting_count
            if total_people_ahead < 0: total_people_ahead = 0

        # 4. Final ETA Calculation
        # For future dates or today before clinic starts, use schedule_start as the baseline
        if now < schedule_start:
            base_time = schedule_start
        else:
            # If the clinic has already started today, use now as the minimum baseline
            base_time = now
        
        minutes_per_patient = 3 if session_type == "晚上" else 5
        estimated_eta = base_time + timedelta(minutes=total_people_ahead * minutes_per_patient)
        
        return estimated_eta.strftime("%H:%M")
    except Exception:
        return None



@router.get("/hospitals", response_model=list[HospitalOut])
async def list_hospitals():
    supabase = get_supabase()
    result = supabase.table("hospitals").select("*").eq("is_active", True).execute()
    return result.data


# CMUH official website category order
CATEGORY_ORDER = [
    "內科部與內科系統",
    "外科部與外科系統",
    "婦兒科系",
    "感官系統",
    "癌症中心或癌症相關",
    "中醫部門系統",
    "精神科",
    "神經暨精神科",
    "健康檢查與體檢相關",
    "其他",
    "內科系",
    "外科系",
    "中醫科系",
    "其他專科",
]


@router.get("/hospitals/{hospital_id}/departments", response_model=list[DepartmentOut])
async def list_departments(hospital_id: str, category: str = Query(default=""), q: str = Query(default="")):
    supabase = get_supabase()
    query = (
        supabase.table("departments")
        .select("*")
        .eq("hospital_id", hospital_id)
        .eq("is_active", True)
        .order("sort_order")
    )
    if category:
        query = query.eq("category", category)
    if q:
        query = query.ilike("name", f"%{q}%")
    result = query.order("name").execute()
    return result.data


@router.get("/hospitals/{hospital_id}/categories")
async def list_department_categories(hospital_id: str):
    """Return distinct department categories for a hospital, ordered by the first appearance in website sequence."""
    supabase = get_supabase()
    result = (
        supabase.table("departments")
        .select("category")
        .eq("hospital_id", hospital_id)
        .eq("is_active", True)
        .order("sort_order")
        .execute()
    )
    
    # Maintain order of first appearance based on scraped sequence
    ordered_categories = []
    seen = set()
    for r in result.data:
        cat = r.get("category")
        if cat and cat not in seen:
            seen.add(cat)
            ordered_categories.append(cat)
            
    return ordered_categories



@router.get("/departments/{department_id}", response_model=DepartmentOut)
async def get_department(department_id: str):
    supabase = get_supabase()
    result = (
        supabase.table("departments")
        .select("*")
        .eq("id", department_id)
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Department not found")
    return result.data


@router.get("/departments/{department_id}/doctors", response_model=list[DoctorOut])
async def list_doctors(department_id: str):
    supabase = get_supabase()
    result = (
        supabase.table("doctors")
        .select("*")
        .eq("department_id", department_id)
        .eq("is_active", True)
        .execute()
    )
    return result.data


@router.get("/hospitals/{hospital_id}/doctors", response_model=list[DoctorOut])
async def list_all_doctors(
    hospital_id: str, 
    department_id: str = Query(default=None, description="過濾特定科室"),
    q: str = Query(default="", description="搜尋醫師名稱")
):
    supabase = get_supabase()
    query = (
        supabase.table("doctors")
        .select("id, hospital_id, department_id, doctor_no, name, specialty, is_active, departments(name)")
        .eq("hospital_id", hospital_id)
        .eq("is_active", True)
    )
    if department_id:
        query = query.eq("department_id", department_id)
    if q:
        query = query.ilike("name", f"%{q}%")
        
    result = query.execute()
    
    docs = []
    for d in result.data:
        dept = d.pop("departments", None)
        d["department_name"] = dept.get("name") if isinstance(dept, dict) else None
        docs.append(d)
        
    return docs


@router.get("/doctors/{doctor_id}/snapshots", response_model=list[SnapshotOut])
async def get_doctor_snapshots(
    doctor_id: str,
    limit: int = Query(default=100, le=200),
):
    supabase = get_supabase()
    result = (
        supabase.table("appointment_snapshots")
        .select("*")
        .eq("doctor_id", doctor_id)
        .order("session_date", desc=False)
        .limit(limit)
        .execute()
    )
    
    data = result.data or []
    for snapshot in data:
        snapshot["eta"] = calculate_eta(
            snapshot.get("session_date"),
            snapshot.get("session_type"),
            snapshot.get("current_number"),
            snapshot.get("current_registered"),
            snapshot.get("waiting_list")
        )
    return data


@router.get("/doctors/{doctor_id}/latest", response_model=SnapshotOut | None)
async def get_doctor_latest_snapshot(doctor_id: str):
    """Get the most recent snapshot for a doctor."""
    supabase = get_supabase()
    result = (
        supabase.table("appointment_snapshots")
        .select("*")
        .eq("doctor_id", doctor_id)
        .order("scraped_at", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
        
    snapshot = result.data[0]
    snapshot["eta"] = calculate_eta(
        snapshot.get("session_date"),
        snapshot.get("session_type"),
        snapshot.get("current_number"),
        snapshot.get("current_registered"),
        snapshot.get("waiting_list")
    )
    return snapshot


@router.get("/doctors/{doctor_id}/schedules")
async def get_doctor_schedules(doctor_id: str):
    """Return distinct session_date + session_type pairs available for this doctor."""
    supabase = get_supabase()
    result = (
        supabase.table("appointment_snapshots")
        .select("session_date, session_type")
        .eq("doctor_id", doctor_id)
        .order("session_date", desc=False)
        .execute()
    )
    # Deduplicate (session_date, session_type) pairs preserving order
    seen = set()
    schedules = []
    for row in result.data:
        key = (row["session_date"], row.get("session_type") or "")
        if key not in seen:
            seen.add(key)
            schedules.append({
                "session_date": row["session_date"],
                "session_type": row.get("session_type")
            })
    return schedules
@router.get("/doctors/{doctor_id}/info")
async def get_doctor_info(doctor_id: str):
    """Get doctor details including department and hospital name."""
    supabase = get_supabase()
    result = (
        supabase.table("doctors")
        .select("id, name, specialty, department_id, departments(name, category, hospital_id, hospitals(name))")
        .eq("id", doctor_id)
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Doctor not found")
    
    data = result.data
    # PostgREST can sometimes return joined objects as a list if it's a 1-to-many relationship
    dept = data.get("departments")
    if isinstance(dept, list) and len(dept) > 0:
        dept = dept[0]
    elif not isinstance(dept, dict):
        dept = {}

    hosp = dept.get("hospitals")
    if isinstance(hosp, list) and len(hosp) > 0:
        hosp = hosp[0]
    elif not isinstance(hosp, dict):
        hosp = {}

    # Fallback: if hospital_name still missing, try direct lookup via hospital_id if available
    h_name = hosp.get("name")
    h_id = dept.get("hospital_id") or data.get("hospital_id")
    if not h_name and h_id:
        h_res = supabase.table("hospitals").select("name").eq("id", h_id).execute()
        if h_res.data:
            h_name = h_res.data[0].get("name")
    
    return {
        "id": data["id"],
        "name": data["name"],
        "specialty": data.get("specialty"),
        "department_id": data.get("department_id"),
        "department_name": dept.get("name") or "（無科室資訊）",
        "department_category": dept.get("category"),
        "hospital_id": h_id,
        "hospital_name": h_name or "（無醫院資訊）"
    }
