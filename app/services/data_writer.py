"""
Data persistence layer: writes scraper output to Supabase.

All Supabase client calls are wrapped with asyncio.to_thread() to prevent
blocking the FastAPI event loop during scheduled scrape tasks.
"""

import asyncio
import re
from datetime import date
from typing import Optional

from app.database import get_supabase
from app.scrapers.base import DepartmentData, DoctorSlot


def _run(fn):
    """Run a synchronous Supabase call in a thread pool executor."""
    return asyncio.to_thread(fn)


def _parse_doctor_name(raw: str) -> tuple[str, Optional[str]]:
    """Split 'Wang醫師(教學診)' into ('Wang醫師', '教學診').

    Parentheses in CMUH doctor names indicate the clinic type/specialty
    for that schedule slot, not part of the doctor's real name.
    """
    m = re.match(r'^(.+?)\((.+?)\)\s*$', raw.strip())
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return raw.strip(), None


async def upsert_department(hosp_id: str, dept: DepartmentData) -> str:
    """Upsert a department and return its UUID."""
    supabase = get_supabase()
    
    # Base row data
    row_data = {"hospital_id": hosp_id, "name": dept.name, "code": dept.code, "sort_order": dept.sort_order}
    if dept.category is not None:
        row_data["category"] = dept.category

    result = await _run(
        lambda: supabase.table("departments")
        .upsert(
            row_data,
            on_conflict="hospital_id,code",
        )
        .execute()
    )
    return result.data[0]["id"]


async def upsert_doctor(hosp_id: str, dept_id: str, slot: DoctorSlot) -> str:
    """Upsert a doctor record (per hospital+dept+doctor_no) and return its UUID.

    The unique key is (hospital_id, doctor_no, department_id) so the same
    doctor appearing in multiple departments gets a separate row per dept.
    Name parentheses are stripped into a separate 'specialty' column.
    """
    supabase = get_supabase()
    clean_name, specialty = _parse_doctor_name(slot.doctor_name)
    row: dict = {
        "hospital_id": hosp_id,
        "department_id": dept_id,
        "doctor_no": slot.doctor_no,
        "name": clean_name,
    }
    if specialty:
        row["specialty"] = specialty
    result = await _run(
        lambda: supabase.table("doctors")
        .upsert(row, on_conflict="hospital_id,doctor_no,department_id")
        .execute()
    )
    return result.data[0]["id"]


async def insert_snapshot(
    doctor_id: str,
    dept_id: str,
    slot: DoctorSlot,
    current_number: Optional[int] = None,
):
    """Insert a single appointment snapshot (non-blocking)."""
    supabase = get_supabase()
    await _run(
        lambda: supabase.table("appointment_snapshots").insert(
            {
                "doctor_id": doctor_id,
                "department_id": dept_id,
                "session_date": str(slot.session_date),
                "session_type": slot.session_type,
                "clinic_room": slot.clinic_room or "",
                "total_quota": slot.total_quota,
                "current_registered": slot.registered,
                "current_number": current_number,
                "is_full": slot.is_full,
                "status": slot.status,
            }
        ).execute()
    )


async def batch_insert_snapshots(rows: list[dict]):
    """Batch upsert multiple appointment snapshots in chunks to avoid server disconnects."""
    if not rows:
        return
    supabase = get_supabase()
    
    chunk_size = 500
    for i in range(0, len(rows), chunk_size):
        chunk = rows[i:i + chunk_size]
        await _run(
            lambda c=chunk: supabase.table("appointment_snapshots")
            .upsert(
                c,
                on_conflict="doctor_id,department_id,session_date,session_type,clinic_room",
            )
            .execute()
        )


async def get_hospital_id(hospital_code: str) -> Optional[str]:
    supabase = get_supabase()
    result = await _run(
        lambda: supabase.table("hospitals")
        .select("id")
        .eq("code", hospital_code)
        .single()
        .execute()
    )
    return result.data["id"] if result.data else None
