from datetime import datetime, date
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, EmailStr, ConfigDict


# ── Hospital ────────────────────────────────────────────────
class HospitalBase(BaseModel):
    name: str
    code: str
    base_url: str

class HospitalOut(HospitalBase):
    id: UUID
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── Department ──────────────────────────────────────────────
class DepartmentOut(BaseModel):
    id: UUID
    hospital_id: UUID
    name: str
    code: str
    category: Optional[str] = None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


# ── Doctor ──────────────────────────────────────────────────
class DoctorOut(BaseModel):
    id: UUID
    hospital_id: UUID
    department_id: Optional[UUID] = None
    department_name: Optional[str] = None
    doctor_no: str
    name: str
    specialty: Optional[str] = None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


# ── AppointmentSnapshot ─────────────────────────────────────
class SnapshotOut(BaseModel):
    id: UUID
    doctor_id: UUID
    department_id: Optional[UUID] = None
    session_date: date
    session_type: Optional[str] = None
    clinic_room: Optional[str] = None
    total_quota: Optional[int] = None
    current_registered: Optional[int] = None
    current_number: Optional[int] = None
    remaining: Optional[int] = None
    is_full: bool
    status: Optional[str] = None
    scraped_at: datetime

    model_config = ConfigDict(from_attributes=True)
