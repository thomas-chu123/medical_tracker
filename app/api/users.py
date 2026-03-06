from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.database import get_supabase
from app.models.user import UserProfileOut, UserProfileUpdate, UserAdminOut
from app.auth import get_current_user, get_current_admin, get_password_hash
from app.core.logger import logger

router = APIRouter(prefix="/api/users", tags=["Users"])


class AdminUserEdit(BaseModel):
    display_name: Optional[str] = None
    new_password: Optional[str] = None


@router.post("/link-line")
async def link_line_account(
    current_user: dict = Depends(get_current_user),
):
    """
    Link the currently logged-in user to the most recent pending LINE User ID from webhook.
    Called after user has scanned QR code and webhook stored the LINE User ID.
    """
    supabase = get_supabase()
    
    try:
        # Check if user already has LINE linked
        user_res = supabase.table("users_local").select("line_user_id").eq("id", current_user["id"]).execute()
        if user_res.data and user_res.data[0].get("line_user_id"):
            return {
                "status": "already_linked",
                "line_user_id": user_res.data[0]["line_user_id"],
                "message": "您的帳號已連接 LINE Bot"
            }
        
        # Find the most recent unexpired pending LINE User ID
        pending_res = supabase.table("line_pending_links").select("id, line_user_id").gt("expires_at", "now()").order("created_at", desc=True).limit(1).execute()
        
        if not pending_res.data:
            return {
                "status": "pending",
                "message": "尚未偵測到 QR Code 掃描。請確保已在 LINE 中加入 Bot。"
            }
        
        pending_link = pending_res.data[0]
        line_user_id = pending_link["line_user_id"]
        
        # Link the LINE User ID to the current user
        update_res = supabase.table("users_local").update({
            "line_user_id": line_user_id
        }).eq("id", current_user["id"]).execute()
        
        # Delete the pending link record
        supabase.table("line_pending_links").delete().eq("id", pending_link["id"]).execute()
        
        return {
            "status": "linked",
            "line_user_id": line_user_id,
            "message": "✓ LINE 連接成功！"
        }
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"連接失敗：{str(e)}")


@router.post("/request-line-reconnect")
async def request_line_reconnect(
    current_user: dict = Depends(get_current_user),
):
    """
    Generate a 6-char code for the user to send in LINE Bot to bind/rebind.

    Works whether or not the user already has a LINE account linked.
    Flow:
    1. User clicks "重新連結" in app settings
    2. Backend generates 6-digit code, stores in line_pending_links with user_id
    3. Frontend displays "bind XXXXXX" + 10-min countdown
    4. User sends that message in LINE Bot
    5. Webhook validates code, writes LINE user_id to users_local
    """
    import asyncio
    from datetime import datetime, timedelta
    import random
    import string

    supabase = get_supabase()

    try:
        # Delete any existing pending links for this user (cleanup before issuing new code)
        await asyncio.to_thread(
            lambda: supabase.table("line_pending_links")
                .delete()
                .eq("user_id", current_user["id"])
                .execute()
        )

        # Generate a temporary 6-character uppercase alphanumeric code
        temp_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

        # Expire in 10 minutes
        expires_at = datetime.utcnow() + timedelta(minutes=10)

        await asyncio.to_thread(
            lambda: supabase.table("line_pending_links").insert({
                "user_id": current_user["id"],
                "temp_code": temp_code,
                "line_user_id": None,
                "expires_at": expires_at.isoformat() + "Z",
            }).execute()
        )

        return {
            "status": "reconnect_request_sent",
            "temp_code": temp_code,
            "expires_at": expires_at.isoformat() + "Z",   # 'Z' suffix = UTC, prevents JS local-time misparse
            "message": f"✓ 請在 LINE Bot 中輸入：bind {temp_code}（10 分鐘內有效）",
        }

    except Exception as e:
        logger.error(f"[LINE Reconnect] Error: {e}")
        raise HTTPException(status_code=400, detail=f"重新連接請求失敗：{str(e)}")


@router.get("/line-status")
async def get_line_status(
    current_user: dict = Depends(get_current_user),
):
    """
    Lightweight polling endpoint: returns wher the user has a LINE account linked.
    Frontend polls this every 3s after issuing a reconnect code.
    """
    supabase = get_supabase()
    res = supabase.table("users_local").select("line_user_id").eq("id", current_user["id"]).execute()
    line_user_id = res.data[0].get("line_user_id") if res.data else None
    return {"line_user_id": line_user_id}




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
    try:
        sub_result = supabase.table("tracking_subscriptions").delete().eq("user_id", user_id).execute()
        logger.info(f"Deleted {len(sub_result.data or [])} tracking subscriptions for user {user_id}")
        
        # Delete the user
        user_result = supabase.table("users_local").delete().eq("id", user_id).execute()
        
        if not user_result.data:
            raise HTTPException(status_code=500, detail="用戶刪除失敗，請重試")
        
        logger.info(f"User {user_id} and associated data deleted successfully")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"User deletion failed for {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="無法刪除用戶，請稍後重試")
    
    return {"message": f"使用者 {target.get('email', user_id)} 已刪除"}
