from fastapi import APIRouter, Query, HTTPException
from app.database import get_supabase
from app.models.hospital import HospitalOut, DepartmentOut, DoctorOut, SnapshotOut

router = APIRouter(prefix="/api", tags=["Hospitals"])


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
]


@router.get("/hospitals/{hospital_id}/departments", response_model=list[DepartmentOut])
async def list_departments(hospital_id: str, category: str = Query(default=""), q: str = Query(default="")):
    supabase = get_supabase()
    query = (
        supabase.table("departments")
        .select("*")
        .eq("hospital_id", hospital_id)
        .eq("is_active", True)
    )
    if category:
        query = query.eq("category", category)
    if q:
        query = query.ilike("name", f"%{q}%")
    result = query.order("name").execute()
    return result.data


@router.get("/hospitals/{hospital_id}/categories")
async def list_department_categories(hospital_id: str):
    """Return distinct department categories for a hospital, ordered by CMUH website order."""
    supabase = get_supabase()
    result = (
        supabase.table("departments")
        .select("category")
        .eq("hospital_id", hospital_id)
        .eq("is_active", True)
        .execute()
    )
    cats_in_db = {r["category"] for r in result.data if r.get("category")}
    # Sort by CMUH official order, unknown categories appended alphabetically at end
    ordered = [c for c in CATEGORY_ORDER if c in cats_in_db]
    extras = sorted(cats_in_db - set(CATEGORY_ORDER))
    return ordered + extras



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
async def list_all_doctors(hospital_id: str, q: str = Query(default="", description="搜尋醫師名稱")):
    supabase = get_supabase()
    query = (
        supabase.table("doctors")
        .select("*")
        .eq("hospital_id", hospital_id)
        .eq("is_active", True)
    )
    if q:
        query = query.ilike("name", f"%{q}%")
    result = query.execute()
    return result.data


@router.get("/doctors/{doctor_id}/snapshots", response_model=list[SnapshotOut])
async def get_doctor_snapshots(
    doctor_id: str,
    limit: int = Query(default=20, le=100),
):
    supabase = get_supabase()
    result = (
        supabase.table("appointment_snapshots")
        .select("*")
        .eq("doctor_id", doctor_id)
        .order("scraped_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data


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
    return result.data[0] if result.data else None


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
