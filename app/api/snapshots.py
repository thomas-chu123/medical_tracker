"""
API endpoints for appointment snapshots.
"""

from fastapi import APIRouter, HTTPException
from app.database import get_supabase
from app.core.timezone import today_tw_str

router = APIRouter(prefix="/api/snapshots", tags=["snapshots"])


@router.get("/{snapshot_id}")
async def get_snapshot(snapshot_id: str):
    """
    Get a specific appointment snapshot with waiting_list data.
    """
    try:
        supabase = get_supabase()
        
        # Fetch snapshot by ID
        result = supabase.table("appointment_snapshots").select(
            "*"
        ).eq("id", snapshot_id).execute()
        
        if not result.data or len(result.data) == 0:
            raise HTTPException(status_code=404, detail="Snapshot not found")
        
        snapshot = result.data[0]
        
        return {
            "id": snapshot.get("id"),
            "doctor_id": snapshot.get("doctor_id"),
            "clinic_room": snapshot.get("clinic_room"),
            "session_date": snapshot.get("session_date"),
            "session_type": snapshot.get("session_type"),
            "current_number": snapshot.get("current_number"),
            "current_registered": snapshot.get("current_registered"),
            "total_quota": snapshot.get("total_quota"),
            "waiting_list": snapshot.get("waiting_list") or [],
            "clinic_queue_details": snapshot.get("clinic_queue_details") or [],
            "status": snapshot.get("status"),
            "scraped_at": snapshot.get("scraped_at"),
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching snapshot: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/doctor/{doctor_id}/current")
async def get_latest_clinic_snapshot(doctor_id: str, clinic_room: str = None):
    """
    Get the latest appointment snapshot for a doctor.
    Optionally filter by clinic_room.
    Prioritize today's session, but fallback to latest available.
    """
    try:
        supabase = get_supabase()
        today = today_tw_str()
        
        # First try: Get today's session
        query = supabase.table("appointment_snapshots").select(
            "*"
        ).eq("doctor_id", doctor_id).eq("session_date", today).order("scraped_at", desc=True).limit(1)
        
        if clinic_room:
            query = query.eq("clinic_room", clinic_room)
        
        result = query.execute()
        
        # If no today's data, try to get the latest snapshot regardless of date
        if not result.data or len(result.data) == 0:
            query_fallback = supabase.table("appointment_snapshots").select(
                "*"
            ).eq("doctor_id", doctor_id).order("session_date", desc=True).order("scraped_at", desc=True).limit(1)
            
            if clinic_room:
                query_fallback = query_fallback.eq("clinic_room", clinic_room)
            
            result = query_fallback.execute()
        
        if not result.data or len(result.data) == 0:
            raise HTTPException(status_code=404, detail="Snapshot not found")
        
        snapshot = result.data[0]
        
        return {
            "id": snapshot.get("id"),
            "doctor_id": snapshot.get("doctor_id"),
            "clinic_room": snapshot.get("clinic_room"),
            "session_date": snapshot.get("session_date"),
            "session_type": snapshot.get("session_type"),
            "current_number": snapshot.get("current_number"),
            "current_registered": snapshot.get("current_registered"),
            "total_quota": snapshot.get("total_quota"),
            "waiting_list": snapshot.get("waiting_list") or [],
            "clinic_queue_details": snapshot.get("clinic_queue_details") or [],
            "status": snapshot.get("status"),
            "scraped_at": snapshot.get("scraped_at"),
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching latest snapshot: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

