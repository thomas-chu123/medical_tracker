from fastapi import APIRouter, Query, HTTPException
from datetime import datetime, date, timedelta
from typing import Optional, List

from app.database import get_supabase
from app.models.hospital import HospitalOut, DepartmentOut, DoctorOut, SnapshotOut
from app.core.timezone import now_tw, today_tw, TAIWAN_TZ

router = APIRouter(prefix="/api", tags=["Hospitals"])

def calculate_eta(
    session_date_str: str,
    session_type: str, 
    current_number: Optional[int],
    registered_count: int, 
    waiting_list: list[int],
    target_number: Optional[int] = None,
    session_speed_mins: Optional[float] = None,
    clinic_queue_details: Optional[list[dict]] = None,
    estimated_wait_minutes: Optional[float] = None,
    waiting_count: int = 0,
) -> Optional[str]:
    """
    Calculate Estimated Appointment Time (ETA).
    - If target_number is NOT provided: Returns the doctor's current estimated progress time.
    - If target_number IS provided: Returns the estimated time for that specific patient.
    
    If estimated_wait_minutes is provided (pre-computed by SpeedEstimator for TVGH/CGH),
    it's used directly as the wait time, giving more accurate ETA than the formula fallback.
    """
    if not session_type or not session_date_str:
        return None
        
    start_times = {
        "上午": "08:30",
        "下午": "13:30",
        "晚上": "18:00"
    }
    
    # 診間持續時間（小時）
    clinic_durations = {
        "上午": 8.25,    # 08:30 - 16:45（8 小時 15 分）
        "下午": 8,       # 13:30 - 21:30（8 小時）
        "晚上": 8        # 18:00 - 02:00 隔日（8 小時）
    }
    
    start_time_str = start_times.get(session_type)
    if not start_time_str:
        return None
        
    try:
        # 1. Date and Time Context
        now = now_tw()
        today = today_tw()
        
        try:
            target_date = datetime.strptime(session_date_str, "%Y-%m-%d").date()
        except ValueError:
            return None

        # 2. Base Start Time Calculation
        schedule_start = datetime.combine(
            target_date, 
            datetime.strptime(start_time_str, "%H:%M").time(),
            tzinfo=TAIWAN_TZ
        )
        
        # 計算診間結束時間
        duration_hours = clinic_durations.get(session_type, 8)
        schedule_end = schedule_start + timedelta(hours=duration_hours)
        
        # 檢查診間是否已結束（當前時間 >= 診間結束時間）
        if now >= schedule_end:
            return "已結束"


        # 3. Calculate how many people are ahead
        total_people_ahead = 0
        if target_number:
            if clinic_queue_details:
                # Use detailed queue information if available (e.g. NTUH)
                # Count people whose number < target and status is NOT "未報到" and NOT "完成"
                # Also ensure they are ahead of current_number
                total_people_ahead = len([
                    item for item in clinic_queue_details 
                    if item.get("number", 0) < target_number 
                    and item.get("number", 0) > (current_number or 0)
                    and item.get("status") not in ["未報到", "完成"]
                ])
            elif waiting_list:
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
            if clinic_queue_details:
                # Count completed patients
                total_people_ahead = len([item for item in clinic_queue_details if item.get("status") == "完成"])
            else:
                waiting_count = len(waiting_list) if waiting_list else 0
                total_people_ahead = (registered_count or 0) - waiting_count
                if total_people_ahead < 0: total_people_ahead = 0

        # 4. Final ETA Calculation
        # base_time is always 'now' (the current real-time), so ETA won't be stale
        if now < schedule_start:
            base_time = schedule_start
        else:
            # If the clinic has already started today, use now as the minimum baseline
            base_time = now

        # If estimated_wait_minutes is pre-computed (by SpeedEstimator for this doctor),
        # use it directly instead of recalculating from total_people_ahead.
        # This gives a more accurate ETA for TVGH/CGH (which provide waiting_count,
        # not a per-number queue, so target-current may not equal people actually waiting).
        if target_number and estimated_wait_minutes is not None:
            estimated_eta = base_time + timedelta(minutes=float(estimated_wait_minutes))
        else:
            if session_speed_mins and session_speed_mins > 0:
                minutes_per_patient = session_speed_mins
            else:
                minutes_per_patient = 3 if session_type == "晚上" else 5
                
            estimated_eta = base_time + timedelta(minutes=total_people_ahead * minutes_per_patient)
        
        # 允許 ETA 超過表定診間結束時間，因為熱門醫師經常會超時看診
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


@router.get("/departments/{department_id}/appointment-snapshots")
async def get_department_appointment_snapshots(
    department_id: str,
    days: int = Query(default=30, ge=1, le=90),
):
    """
    回傳該科室未來排班的輕量索引資料（doctor_id, session_date, session_type）。
    前端用此資料判斷哪個醫師在選定日期/時段有排班，以實作篩選功能。
    """
    supabase = get_supabase()
    today_str = today_tw().isoformat()
    end_date = (today_tw() + timedelta(days=days)).isoformat()

    # 透過 doctors 表取得此 department_id 下的所有 doctor_id
    doctors_res = (
        supabase.table("doctors")
        .select("id")
        .eq("department_id", department_id)
        .eq("is_active", True)
        .execute()
    )
    doctor_ids = [d["id"] for d in (doctors_res.data or [])]
    if not doctor_ids:
        return []

    # 查詢這些醫師的排班快照索引
    result = (
        supabase.table("appointment_snapshots")
        .select("doctor_id, session_date, session_type")
        .in_("doctor_id", doctor_ids)
        .gte("session_date", today_str)
        .lte("session_date", end_date)
        .order("session_date", desc=False)
        .execute()
    )

    # 去重：每個 (doctor_id, session_date, session_type) 只保留一筆
    seen = set()
    index = []
    for row in result.data or []:
        key = (row["doctor_id"], row["session_date"], row.get("session_type") or "")
        if key not in seen:
            seen.add(key)
            index.append({
                "doctor_id": row["doctor_id"],
                "session_date": row["session_date"],
                "session_type": row.get("session_type"),
            })
    return index


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
        # Robustly handle joined department info
        dept = d.pop("departments", None)
        if isinstance(dept, list) and len(dept) > 0:
            dept = dept[0]
        elif not isinstance(dept, dict):
            dept = {}
            
        d["department_name"] = dept.get("name") if dept else None
        docs.append(d)
        
    return docs


@router.get("/doctors/{doctor_id}/snapshots", response_model=list[SnapshotOut])
async def get_doctor_snapshots(
    doctor_id: str,
    limit: int = Query(default=100, le=200),
):
    supabase = get_supabase()
    today_str = today_tw().isoformat()
    result = (
        supabase.table("appointment_snapshots")
        .select("*")
        .eq("doctor_id", doctor_id)
        .gte("session_date", today_str)
        .order("session_date", desc=False)
        .limit(limit)
        .execute()
    )
    
    # Deduplicate: Only one snapshot per (date, session)
    seen = set()
    deduplicated_data = []
    # Data is ordered by session_date ASC. If multiple for same date, later ones in list 
    # (if scraped multiple times) would be more recent IF we ordered by scraped_at.
    # However, since the database now has a unique constraint, this is mostly a safeguard.
    for snapshot in result.data or []:
        key = (snapshot.get("session_date"), snapshot.get("session_type"))
        if key not in seen:
            seen.add(key)
            # Calculate speed per patient if estimated_wait_minutes is available
            session_speed_mins = None
            waiting_count = 0
            if snapshot.get("waiting_list"):
                waiting_count = len(snapshot["waiting_list"])
            elif snapshot.get("clinic_queue_details"):
                for detail in snapshot["clinic_queue_details"]:
                    w = detail.get("waiting_count")
                    if w is not None:
                        waiting_count = w
                        break
            
            if waiting_count > 0 and snapshot.get("estimated_wait_minutes") is not None:
                session_speed_mins = float(snapshot["estimated_wait_minutes"]) / waiting_count

            snapshot["eta"] = calculate_eta(
                snapshot.get("session_date"),
                snapshot.get("session_type"),
                snapshot.get("current_number"),
                snapshot.get("current_registered"),
                snapshot.get("waiting_list"),
                session_speed_mins=session_speed_mins
            )
            deduplicated_data.append(snapshot)
            
    return deduplicated_data


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
    # Calculate speed per patient if estimated_wait_minutes is available
    session_speed_mins = None
    waiting_count = 0
    if snapshot.get("waiting_list"):
        waiting_count = len(snapshot["waiting_list"])
    elif snapshot.get("clinic_queue_details"):
        for detail in snapshot["clinic_queue_details"]:
            w = detail.get("waiting_count")
            if w is not None:
                waiting_count = w
                break
    
    if waiting_count > 0 and snapshot.get("estimated_wait_minutes") is not None:
        session_speed_mins = float(snapshot["estimated_wait_minutes"]) / waiting_count

    snapshot["eta"] = calculate_eta(
        snapshot.get("session_date"),
        snapshot.get("session_type"),
        snapshot.get("current_number"),
        snapshot.get("current_registered"),
        snapshot.get("waiting_list"),
        session_speed_mins=session_speed_mins
    )
    return snapshot


@router.get("/doctors/{doctor_id}/schedules")
async def get_doctor_schedules(doctor_id: str):
    """Return distinct session_date + session_type pairs available for this doctor."""
    supabase = get_supabase()
    today_str = today_tw().isoformat()
    result = (
        supabase.table("appointment_snapshots")
        .select("session_date, session_type")
        .eq("doctor_id", doctor_id)
        .gte("session_date", today_str)
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