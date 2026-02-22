from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.database import get_supabase
from app.models.user import UserProfileOut, UserProfileUpdate, UserAdminOut
from app.auth import get_current_user, get_current_admin, get_password_hash

router = APIRouter(prefix="/api/users", tags=["Users"])


class AdminUserEdit(BaseModel):
    display_name: Optional[str] = None
    new_password: Optional[str] = None


@router.get("/me", response_model=UserProfileOut)
async def get_my_profile(current_user: dict = Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=UserProfileOut)
async def update_my_profile(
    data: UserProfileUpdate,
    current_user: dict = Depends(get_current_user),
):
    supabase = get_supabase()
    update_data = data.model_dump(exclude_none=True)
    if not update_data:
        return current_user

    result = (
        supabase.table("users_local")
        .update(update_data)
        .eq("id", current_user["id"])
        .execute()
    )
    return result.data[0]


@router.get("/", response_model=list[UserAdminOut])
async def list_users(
    admin: dict = Depends(get_current_admin),
    limit: int = 50,
    offset: int = 0,
):
    """Admin only: list all users from local table."""
    supabase = get_supabase()
    result = (
        supabase.table("users_local")
        .select("*")
        .range(offset, offset + limit - 1)
        .execute()
    )
    return result.data


@router.patch("/{user_id}/admin")
async def toggle_admin(
    user_id: str,
    is_admin: bool,
    admin: dict = Depends(get_current_admin),
):
    """Admin only: grant or revoke admin rights."""
    supabase = get_supabase()
    supabase.table("users_local").update({"is_admin": is_admin}).eq("id", user_id).execute()
    return {"message": f"使用者 {user_id} 管理員權限已更新"}


@router.patch("/{user_id}/edit")
async def admin_edit_user(
    user_id: str,
    data: AdminUserEdit,
    admin: dict = Depends(get_current_admin),
):
    """Admin only: update a user's display_name and/or password."""
    supabase = get_supabase()

    # Check target user exists
    res = supabase.table("users_local").select("id, is_admin").eq("id", user_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="找不到使用者")

    update_data: dict = {}
    if data.display_name is not None:
        update_data["display_name"] = data.display_name
    if data.new_password is not None:
        if len(data.new_password) < 8:
            raise HTTPException(status_code=422, detail="密碼至少需要 8 個字元")
        update_data["hashed_password"] = get_password_hash(data.new_password)

    if not update_data:
        return {"message": "無需更新"}

    supabase.table("users_local").update(update_data).eq("id", user_id).execute()
    return {"message": "使用者資料已更新"}


@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    admin: dict = Depends(get_current_admin),
):
    """Admin only: delete a non-admin user."""
    supabase = get_supabase()

    # Fetch target
    res = supabase.table("users_local").select("id, is_admin, email").eq("id", user_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="找不到使用者")

    target = res.data[0]
    if target.get("is_admin"):
        raise HTTPException(status_code=403, detail="無法刪除管理員帳號")
    if user_id == admin["id"]:
        raise HTTPException(status_code=403, detail="無法刪除自己的帳號")

    # Remove related tracking subscriptions first (FK constraint)
    supabase.table("tracking_subscriptions").delete().eq("user_id", user_id).execute()

    # Delete the user
    supabase.table("users_local").delete().eq("id", user_id).execute()
    return {"message": f"使用者 {target.get('email', user_id)} 已刪除"}
