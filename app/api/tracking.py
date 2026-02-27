from datetime import date
from typing import Optional
from uuid import UUID
import asyncio

from fastapi import APIRouter, Depends, HTTPException, status

from app.database import get_supabase
from app.models.tracking import TrackingCreate, TrackingUpdate, TrackingOut, TrackingRichOut, NotificationLogOut, NotificationLogRichOut
from app.auth import get_current_user

from app.core.timezone import today_tw_str

router = APIRouter(prefix="/api/tracking", tags=["Tracking"])

@router.get("/", response_model=list[TrackingRichOut])
async def list_subscriptions(current_user: dict = Depends(get_current_user)):
    """
    Fetch user's tracking subscriptions with enriched data (doctors, departments, hospitals, current numbers).
    All database queries run in parallel to maximize speed.
    """
    supabase = get_supabase()
    
    # 1. Fetch subscriptions
    subs_result = await asyncio.to_thread(
        lambda: supabase.table("tracking_subscriptions")
        .select("*")
        .eq("user_id", current_user["id"])
        .order("session_date", desc=False)
        .execute()
    )
    subs = subs_result.data

    if not subs:
        return []

    # Extract IDs to fetch
    doctor_ids = list({s["doctor_id"] for s in subs if s.get("doctor_id")})
    dept_ids_set = {s["department_id"] for s in subs if s.get("department_id")}
    tracked_dates = list({s["session_date"] for s in subs})
    
    # Initialize result maps
    doctors_map = {}
    depts_map = {}
    hospitals_map = {}
    current_numbers = {}
    doctor_latest_rooms = {}
    
    # 2. Parallel fetch all related data (only if needed)
    if doctor_ids:
        # Helper function to fetch doctors (synchronous, runs in thread pool)
        def _fetch_doctors():
            return supabase.table("doctors").select("id, name, specialty, hospital_id, department_id").in_("id", doctor_ids).execute()
        
        # Helper function to fetch latest snapshots
        def _fetch_latest_snaps():
            return supabase.table("appointment_snapshots").select("doctor_id, clinic_room").in_("doctor_id", doctor_ids).order("scraped_at", desc=True).execute()
        
        # Helper function to fetch snapshots by date
        def _fetch_snapshot_data():
            if not tracked_dates:
                return None
            date_strs = [d.isoformat() if isinstance(d, date) else str(d) for d in tracked_dates]
            return supabase.table("appointment_snapshots").select("doctor_id, session_date, session_type, clinic_room, current_number, total_quota, current_registered, remaining, status, waiting_list").in_("doctor_id", doctor_ids).in_("session_date", date_strs).order("scraped_at", desc=True).execute()
        
        # Run all in parallel
        docs_result, latest_snaps_result, snapshot_result = await asyncio.gather(
            asyncio.to_thread(_fetch_doctors),
            asyncio.to_thread(_fetch_latest_snaps),
            asyncio.to_thread(_fetch_snapshot_data),
        )
        
        # Build maps from results
        if docs_result and docs_result.data:
            doctors_map = {d["id"]: d for d in docs_result.data}
            
            # Fetch hospitals
            hospital_ids = list({d.get("hospital_id") for d in docs_result.data if d.get("hospital_id")})
            if hospital_ids:
                def _fetch_hospitals():
                    return supabase.table("hospitals").select("id, name").in_("id", hospital_ids).execute()
                
                hosps = await asyncio.to_thread(_fetch_hospitals)
                if hosps and hosps.data:
                    hospitals_map = {h["id"]: h["name"] for h in hosps.data}
        
        if latest_snaps_result and latest_snaps_result.data:
            for ls in latest_snaps_result.data:
                d_id = ls["doctor_id"]
                if d_id not in doctor_latest_rooms and ls.get("clinic_room"):
                    doctor_latest_rooms[d_id] = ls["clinic_room"]
        
        if snapshot_result and snapshot_result.data:
            for snap in snapshot_result.data:
                key = (snap["doctor_id"], snap["session_date"], snap["session_type"])
                if key not in current_numbers:
                    current_numbers[key] = snap
    
    # 3. Fetch departments if needed
    if dept_ids_set:
        def _fetch_depts():
            return supabase.table("departments").select("id, name, category").in_("id", list(dept_ids_set)).execute()
        
        depts = await asyncio.to_thread(_fetch_depts)
        if depts and depts.data:
            depts_map = {d["id"]: d for d in depts.data}
    
    # 4. Enrich subscriptions with fetched data
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
        
        # Calculate ETA
        from app.api.hospitals import calculate_eta
        s["eta"] = calculate_eta(
            s["session_date"],
            s["session_type"],
            s.get("current_number"),
            s.get("current_registered"),
            s.get("waiting_list"),
            target_number=s.get("appointment_number")
        )

        # Clinic room fallback
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
        raise HTTPException(status_code=404, detail="Doctor not found")

    # Insert subscription
    sub_data = data.model_dump(mode="json")
    sub_data["user_id"] = str(current_user["id"])
    sub_data["is_active"] = True

    sub = supabase.table("tracking_subscriptions").insert(sub_data).execute()

    return TrackingOut(**sub.data[0])


@router.patch("/{sub_id}", response_model=TrackingOut)
async def update_subscription(
    sub_id: str,
    data: TrackingUpdate,
    current_user: dict = Depends(get_current_user),
):
    supabase = get_supabase()

    # Verify ownership
    sub = supabase.table("tracking_subscriptions").select("id").eq("id", sub_id).eq("user_id", current_user["id"]).execute()
    if not sub.data:
        raise HTTPException(status_code=404, detail="Subscription not found")

    # Update
    update_dict = data.model_dump(mode="json", exclude_unset=True)
    result = supabase.table("tracking_subscriptions").update(update_dict).eq("id", sub_id).execute()

    return TrackingOut(**result.data[0])


@router.delete("/{sub_id}", status_code=204)
async def delete_subscription(
    sub_id: str,
    current_user: dict = Depends(get_current_user),
):
    supabase = get_supabase()

    # Verify ownership
    sub = supabase.table("tracking_subscriptions").select("id").eq("id", sub_id).eq("user_id", current_user["id"]).execute()
    if not sub.data:
        raise HTTPException(status_code=404, detail="Subscription not found")

    supabase.table("tracking_subscriptions").delete().eq("id", sub_id).execute()


@router.get("/logs/all", response_model=list[NotificationLogRichOut])
async def get_all_notification_logs(
    current_user: dict = Depends(get_current_user),
    limit: int = 100,
    offset: int = 0,
):
    """Fetch all notification logs for the current user's tracked subscriptions."""
    import asyncio
    import logging
    
    log = logging.getLogger(__name__)
    supabase = get_supabase()

    # Fetch user's subscriptions with all detail needed
    subs_res = supabase.table("tracking_subscriptions").select("*").eq("user_id", current_user["id"]).execute()
    if not subs_res.data:
        log.info(f"[NotifAPI] No subscriptions found for user {current_user['id']}")
        return []
    
    sub_ids = [s["id"] for s in subs_res.data]
    sub_map = {s["id"]: s for s in subs_res.data}
    
    # Fetch logs
    logs_res = supabase.table("notification_logs").select("*").in_("subscription_id", sub_ids).order("sent_at", desc=True).limit(limit).offset(offset).execute()
    
    if not logs_res.data:
        log.info(f"[NotifAPI] No notification logs found for user {current_user['id']}")
        return []

    # Collect unique doctor_ids and clinic_ids
    doctor_ids = set()
    clinic_ids = set()
    
    for log_entry in logs_res.data:
        sub = sub_map.get(log_entry["subscription_id"])
        if sub:
            if sub.get("doctor_id"):
                doctor_ids.add(sub["doctor_id"])
            if sub.get("clinic_id"):
                clinic_ids.add(sub["clinic_id"])
    
    # Batch fetch all doctors and clinics in parallel
    def _fetch_doctors():
        if not doctor_ids:
            return {}
        docs = supabase.table("doctors").select("id, name, hospital_id").in_("id", list(doctor_ids)).execute()
        return {d["id"]: d for d in docs.data}
    
    def _fetch_clinics():
        if not clinic_ids:
            return {}
        clinics = supabase.table("clinics").select("id, clinic_date, session_type, hospital_id, department_id, room").in_("id", list(clinic_ids)).execute()
        return {c["id"]: c for c in clinics.data}
    
    # Execute in parallel
    doctor_map, clinic_map = await asyncio.gather(
        asyncio.to_thread(_fetch_doctors),
        asyncio.to_thread(_fetch_clinics)
    )
    
    # Collect all hospital and department IDs needed
    hospital_ids = set()
    department_ids = set()
    
    for doctor in doctor_map.values():
        if doctor.get("hospital_id"):
            hospital_ids.add(doctor["hospital_id"])
    
    for clinic in clinic_map.values():
        if clinic.get("hospital_id"):
            hospital_ids.add(clinic["hospital_id"])
        if clinic.get("department_id"):
            department_ids.add(clinic["department_id"])
    
    for sub in sub_map.values():
        if sub.get("hospital_id"):
            hospital_ids.add(sub["hospital_id"])
    
    # Batch fetch hospitals and departments
    def _fetch_hospitals():
        if not hospital_ids:
            return {}
        hosps = supabase.table("hospitals").select("id, name").in_("id", list(hospital_ids)).execute()
        return {h["id"]: h["name"] for h in hosps.data}
    
    def _fetch_departments():
        if not department_ids:
            return {}
        depts = supabase.table("departments").select("id, name").in_("id", list(department_ids)).execute()
        return {d["id"]: d["name"] for d in depts.data}
    
    hospital_map, department_map = await asyncio.gather(
        asyncio.to_thread(_fetch_hospitals),
        asyncio.to_thread(_fetch_departments)
    )
    
    # Enrich logs with all available data
    enriched = []
    for log_entry in logs_res.data:
        sub = sub_map.get(log_entry["subscription_id"])
        if not sub:
            continue
        
        doctor_id = sub.get("doctor_id")
        doctor = doctor_map.get(doctor_id) if doctor_id else None
        clinic_id = sub.get("clinic_id")
        clinic = clinic_map.get(clinic_id) if clinic_id else None
        
        # Prefer clinic hospital, fallback to doctor hospital, fallback to sub hospital, fallback to logged value
        hospital_id = clinic.get("hospital_id") if clinic else (doctor.get("hospital_id") if doctor else sub.get("hospital_id"))
        hospital_name = log_entry.get("hospital_name") or hospital_map.get(hospital_id, "Unknown") if hospital_id else (log_entry.get("hospital_name") or "Unknown")
        
        # Prefer values stored in notification_logs, then fallback to current data
        enriched_log = {
            **log_entry,
            "doctor_name": log_entry.get("doctor_name") or (doctor.get("name", "Unknown") if doctor else "Unknown"),
            "session_date": log_entry.get("session_date") or (clinic.get("clinic_date") if clinic else sub.get("session_date")),
            "session_type": log_entry.get("session_type") or (clinic.get("session_type") if clinic else sub.get("session_type")),
            "hospital_name": hospital_name,
            "department_name": log_entry.get("department_name") or (department_map.get(clinic.get("department_id"), "Unknown") if clinic else (sub.get("department_name") or "Unknown")),
            "clinic_room": log_entry.get("clinic_room") or (clinic.get("room") if clinic else None),
            "current_number": log_entry.get("current_number"),
        }
        enriched.append(enriched_log)

    log.info(f"[NotifAPI] Returning {len(enriched)} enriched logs for user {current_user['id']}")
    return enriched


@router.get("/logs/debug")
async def debug_notification_logs(current_user: dict = Depends(get_current_user)):
    """Debug endpoint to check notification_logs data in Supabase."""
    supabase = get_supabase()
    
    # Check user's subscriptions
    subs = supabase.table("tracking_subscriptions").select("id").eq("user_id", current_user["id"]).execute()
    sub_ids = [s["id"] for s in subs.data]
    
    # Check total notification logs for this user
    total_logs = supabase.table("notification_logs").select("*", count="exact").in_("subscription_id", sub_ids).execute()
    
    # Get sample logs
    sample_logs = supabase.table("notification_logs").select("*").in_("subscription_id", sub_ids).order("sent_at", desc=True).limit(5).execute()
    
    return {
        "user_id": current_user["id"],
        "subscriptions_count": len(sub_ids),
        "total_notification_logs": total_logs.count if hasattr(total_logs, 'count') else len(total_logs.data),
        "sample_logs": sample_logs.data,
        "sample_logs_count": len(sample_logs.data),
    }
