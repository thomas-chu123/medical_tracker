from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.database import get_supabase
from app.models.tracking import TrackingCreate, TrackingUpdate, TrackingOut, TrackingRichOut, NotificationLogOut
from app.auth import get_current_user

router = APIRouter(prefix="/api/tracking", tags=["Tracking"])

# Taiwan timezone (UTC+8)
_TW_TZ = timezone(timedelta(hours=8))


def _tw_today() -> str:
    """Return today's date string in Taiwan time (UTC+8)."""
    return datetime.now(_TW_TZ).date().isoformat()

@router.get("/", response_model=list[TrackingRichOut])
async def list_subscriptions(current_user: dict = Depends(get_current_user)):
    supabase = get_supabase()
    result = (
        supabase.table("tracking_subscriptions")
        .select("*")
        .eq("user_id", current_user["id"])
        .gte("session_date", _tw_today())  # Only show today and future sessions
        .order("session_date", desc=False)
        .execute()
    )
    subs = result.data

    if not subs:
        return []

    # Batch-fetch doctors and departments to prevent N+1
    doctor_ids = list({s["doctor_id"] for s in subs if s.get("doctor_id")})
    
    doctors_map = {}
    if doctor_ids:
        docs = supabase.table("doctors").select("id, name, specialty, hospital_id, department_id").in_("id", doctor_ids).execute()
        doctors_map = {d["id"]: d for d in docs.data}

    # Collect department IDs from both subs and their doctors (as fallback)
    dept_ids_set = {s["department_id"] for s in subs if s.get("department_id")}
    for d in doctors_map.values():
        if d.get("department_id"):
            dept_ids_set.add(d["department_id"])
    
    dept_ids = list(dept_ids_set)
    depts_map = {}
    if dept_ids:
        depts = supabase.table("departments").select("id, name, category").in_("id", dept_ids).execute()
        depts_map = {d["id"]: d for d in depts.data}

    # Fetch hospital names for doctors
    hospital_ids = list({d.get("hospital_id") for d in doctors_map.values() if d.get("hospital_id")})
    hospitals_map = {}
    if hospital_ids:
        hosps = supabase.table("hospitals").select("id, name").in_("id", hospital_ids).execute()
        hospitals_map = {h["id"]: h["name"] for h in hosps.data}

    # Fetch latest current_number for these tracked sessions
    now_date_str = _tw_today()  # Use Taiwan time
    # We only care about snapshots for the tracked session dates
    tracked_dates = list({s["session_date"] for s in subs})
    
    current_numbers = {}
    doctor_latest_rooms = {}
    if doctor_ids:
        # 1. Fetch the most recent snapshot for each doctor/date/session_type combination (precise match)
        if tracked_dates:
            try:
                date_strs = [d.isoformat() if isinstance(d, date) else str(d) for d in tracked_dates]
                snaps = (
                    supabase.table("appointment_snapshots")
                    .select("doctor_id, session_date, session_type, clinic_room, current_number, total_quota, current_registered, remaining, status, waiting_list")
                    .in_("doctor_id", doctor_ids)
                    .in_("session_date", date_strs)
                    .order("scraped_at", desc=True)
                    .execute()
                )
                for snap in snaps.data:
                    key = (snap["doctor_id"], snap["session_date"], snap["session_type"])
                    if key not in current_numbers:
                        current_numbers[key] = snap
            except Exception as e:
                print(f"Error fetching clinic snapshots: {e}")

        # 2. Fetch latest snapshot per doctor regardless of date (as fallback for clinic_room)
        try:
            # We can't easily do a limit-per-group in Supabase select, so we fetch recent snaps and dedupe
            # or better: use the existing scraped room if available.
            # For now, let's just fetch the absolute latest scan for each doctor.
            latest_snaps = (
                supabase.table("appointment_snapshots")
                .select("doctor_id, clinic_room")
                .in_("doctor_id", doctor_ids)
                .order("scraped_at", desc=True)
                .execute()
            )
            for ls in latest_snaps.data:
                d_id = ls["doctor_id"]
                if d_id not in doctor_latest_rooms and ls.get("clinic_room"):
                    doctor_latest_rooms[d_id] = ls["clinic_room"]
        except Exception as e:
            print(f"Error fetching latest rooms: {e}")

    # Attach doctor/dept/hospital info & current_number to each sub
    enriched = []
    for s in subs:
        doc = doctors_map.get(s.get("doctor_id"), {})
        d_id = s.get("department_id") or doc.get("department_id")
        dept = depts_map.get(d_id, {})
        
        hosp_name = hospitals_map.get(doc.get("hospital_id"), "")
        s["doctor_name"] = doc.get("name", "")
        s["department_name"] = dept.get("name", "")
        s["hospital_name"] = hosp_name
        
        # Determine current_number and clinic_room
        key = (s["doctor_id"], s["session_date"], s["session_type"])
        snap_info = current_numbers.get(key, {})
        
        s["current_number"] = snap_info.get("current_number")
        s["total_quota"] = snap_info.get("total_quota")
        s["current_registered"] = snap_info.get("current_registered")
        s["remaining"] = snap_info.get("remaining")
        s["status"] = snap_info.get("status")
        s["waiting_list"] = snap_info.get("waiting_list")
        
        # Calculate ETA (import helper from hospitals)
        from app.api.hospitals import calculate_eta
        s["eta"] = calculate_eta(
            s["session_date"],
            s["session_type"],
            s.get("current_number"),
            s.get("current_registered"),
            s.get("waiting_list"),
            target_number=s.get("appointment_number")
        )

        # Clinic room fallback: prioritize specific session, then latest known
        s["clinic_room"] = snap_info.get("clinic_room") or doctor_latest_rooms.get(s["doctor_id"])
        
        enriched.append(s)

    return enriched


@router.post("/", response_model=TrackingOut, status_code=201)
async def create_subscription(
    data: TrackingCreate,
    current_user: dict = Depends(get_current_user),
):
    supabase = get_supabase()

    # Verify doctor exists
    doc = supabase.table("doctors").select("id").eq("id", str(data.doctor_id)).execute()
    if not doc.data:
        raise HTTPException(status_code=404, detail="找不到醫師")

    payload = data.model_dump()
    payload["user_id"] = current_user["id"]
    payload["doctor_id"] = str(payload["doctor_id"])
    if payload.get("department_id"):
        payload["department_id"] = str(payload["department_id"])
    payload["session_date"] = str(payload["session_date"])

    try:
        result = supabase.table("tracking_subscriptions").insert(payload).execute()
    except Exception as e:
        if "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail="您已追蹤此門診")
        raise HTTPException(status_code=400, detail=str(e))

    return result.data[0]


@router.patch("/{sub_id}", response_model=TrackingOut)
async def update_subscription(
    sub_id: str,
    data: TrackingUpdate,
    current_user: dict = Depends(get_current_user),
):
    supabase = get_supabase()
    existing = (
        supabase.table("tracking_subscriptions")
        .select("id")
        .eq("id", sub_id)
        .eq("user_id", current_user["id"])
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="找不到追蹤設定")

    update_data = data.model_dump(exclude_none=True)
    result = (
        supabase.table("tracking_subscriptions")
        .update(update_data)
        .eq("id", sub_id)
        .execute()
    )
    return result.data[0]


@router.delete("/{sub_id}", status_code=204)
async def delete_subscription(
    sub_id: str,
    current_user: dict = Depends(get_current_user),
):
    supabase = get_supabase()
    existing = (
        supabase.table("tracking_subscriptions")
        .select("id")
        .eq("id", sub_id)
        .eq("user_id", current_user["id"])
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="找不到追蹤設定")

    supabase.table("tracking_subscriptions").delete().eq("id", sub_id).execute()


@router.get("/{sub_id}/logs", response_model=list[NotificationLogOut])
async def get_notification_logs(
    sub_id: str,
    current_user: dict = Depends(get_current_user),
):
    supabase = get_supabase()
    existing = (
        supabase.table("tracking_subscriptions")
        .select("id")
        .eq("id", sub_id)
        .eq("user_id", current_user["id"])
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="找不到追蹤設定")

    result = (
        supabase.table("notification_logs")
        .select("*")
        .eq("subscription_id", sub_id)
        .order("sent_at", desc=True)
        .execute()
    )
    return result.data
@router.get("/debug/cmuh/{room}/{period}")
async def debug_cmuh(room: str, period: str):
    from app.scrapers.cmuh import CMUHScraper
    scraper = CMUHScraper()
    try:
        prog = await scraper.fetch_clinic_progress(room, period)
        return {"success": True, "progress": prog}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        await scraper.close()
