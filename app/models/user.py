from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, EmailStr, field_validator


# ── Auth schemas ────────────────────────────────────────────
class UserRegister(BaseModel):
    email: EmailStr
    password: str
    display_name: Optional[str] = None

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("密碼至少需要 8 個字元")
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    user_id: Optional[str] = None


# ── User Profile ────────────────────────────────────────────
class UserProfile(BaseModel):
    id: UUID
    email: str
    display_name: Optional[str] = None
    line_notify_token: Optional[str] = None
    is_admin: bool = False
    is_verified: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


class UserProfileOut(BaseModel):
    id: UUID
    display_name: Optional[str] = None
    line_notify_token: Optional[str] = None
    is_admin: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


class UserProfileUpdate(BaseModel):
    display_name: Optional[str] = None
    line_notify_token: Optional[str] = None


# ── Admin user listing ──────────────────────────────────────
class UserAdminOut(BaseModel):
    id: UUID
    email: Optional[str] = None
    display_name: Optional[str] = None
    is_admin: bool = False
    is_verified: bool = False
    created_at: datetime

    class Config:
        from_attributes = True
