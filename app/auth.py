from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from app.config import get_settings
from app.database import get_supabase
from app.models.user import TokenData

from passlib.context import CryptContext
from app.config import get_settings
from app.database import get_supabase
from app.models.user import TokenData

settings = get_settings()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password, hashed_password):
    # Truncate plain_password to 71 bytes to avoid bcrypt >72 byte ValueError
    # passlib sometimes struggles with this wrapper depending on pyca/cryptography version
    password_bytes = plain_password.encode('utf-8')[:71]
    return pwd_context.verify(password_bytes.decode('utf-8', 'ignore'), hashed_password)


def get_password_hash(password):
    password_bytes = password.encode('utf-8')[:71]
    return pwd_context.hash(password_bytes.decode('utf-8', 'ignore'))


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="無法驗證憑證",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    supabase = get_supabase()
    result = supabase.table("users_local").select("*").eq("id", user_id).execute()
    if not result.data:
        raise credentials_exception
    
    user = result.data[0]
    return user


async def get_current_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="需要管理員權限")
    return current_user


async def seed_super_user():
    """Called at startup – ensures the 'super' admin account exists."""
    SUPER_EMAIL = "super@admin.system"
    SUPER_PASSWORD = "supersuper"

    supabase = get_supabase()
    try:
        result = supabase.table("users_local").select("id").eq("email", SUPER_EMAIL).execute()
        if result.data:
            return  # already exists

        hashed = get_password_hash(SUPER_PASSWORD)
        supabase.table("users_local").insert({
            "email": SUPER_EMAIL,
            "hashed_password": hashed,
            "display_name": "Super Admin",
            "is_admin": True,
            "is_verified": True,
        }).execute()
        print("[auth] ✅ Super admin account created (email: super@admin.local)")
    except Exception as e:
        print(f"[auth] ⚠️  Could not seed super user: {e}")
