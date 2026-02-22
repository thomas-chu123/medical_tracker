from datetime import date, datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel


# ── Create / Update ─────────────────────────────────────────
class TrackingCreate(BaseModel):
    doctor_id: UUID
    department_id: Optional[UUID] = None
    session_date: date
    session_type: Optional[str] = None  # '上午' / '下午' / '晚上'
    appointment_number: Optional[int] = None
    notify_at_20: bool = True
    notify_at_10: bool = True
    notify_at_5: bool = True
    notify_email: bool = True
    notify_line: bool = False


class TrackingUpdate(BaseModel):
    notify_at_20: Optional[bool] = None
    notify_at_10: Optional[bool] = None
    notify_at_5: Optional[bool] = None
    notify_email: Optional[bool] = None
    notify_line: Optional[bool] = None
    is_active: Optional[bool] = None


# ── Response ─────────────────────────────────────────────────
class TrackingOut(BaseModel):
    id: UUID
    user_id: UUID
    doctor_id: UUID
    department_id: Optional[UUID] = None
    session_date: date
    session_type: Optional[str] = None
    appointment_number: Optional[int] = None
    notify_at_20: bool
    notify_at_10: bool
    notify_at_5: bool
    notify_email: bool
    notify_line: bool
    notified_20: bool
    notified_10: bool
    notified_5: bool
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class TrackingRichOut(TrackingOut):
    """TrackingOut enriched with joined doctor/dept/hospital names."""
    doctor_name: Optional[str] = None
    department_name: Optional[str] = None
    hospital_name: Optional[str] = None

    class Config:
        from_attributes = True


class AdminTrackingOut(TrackingRichOut):
    """Admin view of tracking with user details."""
    user_email: Optional[str] = None
    user_name: Optional[str] = None

    class Config:
        from_attributes = True


class NotificationLogOut(BaseModel):
    id: UUID
    subscription_id: UUID
    threshold: int
    channel: str
    sent_at: datetime
    success: bool
    error_message: Optional[str] = None

    class Config:
        from_attributes = True
