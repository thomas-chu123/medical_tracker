from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.database import get_supabase
from app.models.tracking import TrackingCreate, TrackingUpdate, TrackingOut, TrackingRichOut, NotificationLogOut
from app.auth import get_current_user

router = APIRouter(prefix="/api/tracking", tags=["Tracking"])


@router.get("/", response_model=list[TrackingRichOut])
async def list_subscriptions(current_user: dict = Depends(get_current_user)):
    supabase = get_supabase()
    result = (
        supabase.table("tracking_subscriptions")
        .select("*")
        .eq("user_id", current_user["id"])
        .order("session_date", desc=False)
        .execute()
    )
    subs = result.data

    if not subs:
        return []

    # Batch-fetch doctors and departments to avoid N+1
    doctor_ids = list({s["doctor_id"] for s in subs if s.get("doctor_id")})
    dept_ids = list({s["department_id"] for s in subs if s.get("department_id")})

    doctors_map = {}
    if doctor_ids:
        docs = supabase.table("doctors").select("id, name, specialty, hospital_id").in_("id", doctor_ids).execute()
        doctors_map = {d["id"]: d for d in docs.data}

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

    # Attach doctor/dept/hospital info to each sub
    enriched = []
    for s in subs:
        doc = doctors_map.get(s.get("doctor_id"), {})
        dept = depts_map.get(s.get("department_id"), {})
        hosp_name = hospitals_map.get(doc.get("hospital_id"), "")
        s["doctor_name"] = doc.get("name", "")
        s["department_name"] = dept.get("name", "")
        s["hospital_name"] = hosp_name
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
