"""LINE Message API Webhook handler."""

import base64
import hashlib
import hmac
import json
from fastapi import APIRouter, Request, HTTPException
from app.config import get_settings
from app.database import get_supabase

settings = get_settings()
router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post("/line")
async def line_webhook(request: Request):
    """
    Handle LINE Message API webhook events.
    
    Webhook events:
    - follow: User adds the bot as a friend
    - unfollow: User removes the bot
    - message: User sends a message to the bot
    """
    
    # Get request body
    body = await request.body()
    
    # Verify signature
    signature = request.headers.get("x-line-signature")
    if not signature:
        raise HTTPException(status_code=403, detail="Missing X-LINE-Signature header")
    
    if not _verify_signature(body, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")
    
    # Parse events
    data = json.loads(body)
    
    for event in data.get("events", []):
        try:
            if event["type"] == "follow":
                user_id = event["source"]["userId"]
                await _handle_user_follow(user_id)
            
            elif event["type"] == "unfollow":
                user_id = event["source"]["userId"]
                await _handle_user_unfollow(user_id)
            
            elif event["type"] == "message":
                user_id = event["source"]["userId"]
                message_text = event["message"].get("text", "")
                await _handle_user_message(user_id, message_text)
        
        except Exception as e:
            print(f"[LINE Webhook] Error processing event: {e}")
            # Continue processing other events
    
    return {"status": "ok"}


def _verify_signature(body: bytes, signature: str) -> bool:
    """Verify LINE webhook signature."""
    if not settings.line_channel_secret:
        print("[LINE] No Channel Secret configured, skipping verification")
        return False
    
    hash_object = hmac.new(
        settings.line_channel_secret.encode('utf-8'),
        body,
        hashlib.sha256
    )
    expected_signature = base64.b64encode(hash_object.digest()).decode()
    
    return signature == expected_signature


async def _handle_user_follow(user_id: str):
    """
    Handle user following the bot.
    
    When a user adds the bot as a friend:
    - Check if there's an existing user with this LINE User ID
    - If found, update their record
    - If not found, store it (they'll match when they register/login)
    - Send welcome message
    """
    print(f"[LINE] User {user_id} followed the bot")
    
    try:
        supabase = get_supabase()
        
        # Check if a user with this LINE User ID already exists
        result = supabase.table("users_local").select("id").eq("line_user_id", user_id).execute()
        
        if result.data:
            # User exists, just confirm the follow
            print(f"[LINE] User {user_id} is already registered")
        else:
            # User doesn't exist yet, store the LINE User ID
            # They will match it to their account when they register/login
            # For now, we don't update any user (they haven't registered yet)
            print(f"[LINE] New user {user_id} - waiting for registration")
        
        # Send welcome message (works even if they haven't registered)
        from app.services.line_message_api import send_line_message
        await send_line_message(
            user_id,
            "歡迎使用台灣醫療門診追蹤系統！\n\n"
            "若尚未註冊，請先在應用中建立帳號。\n"
            "建立帳號時，您的 LINE User ID 會自動收集。\n\n"
            "之後可在應用中設置要追蹤的醫師，並啟用 LINE 通知。"
        )
    
    except Exception as e:
        print(f"[LINE] Error handling follow event: {e}")


async def _handle_user_unfollow(user_id: str):
    """
    Handle user unfollowing the bot.
    
    - Clear LINE User ID from their account
    - Disable all LINE notifications for this user
    """
    print(f"[LINE] User {user_id} unfollowed the bot")
    
    try:
        supabase = get_supabase()
        
        # Find user by LINE User ID and clear it
        user_result = supabase.table("users_local").select("id").eq("line_user_id", user_id).execute()
        
        if user_result.data:
            user_local_id = user_result.data[0]["id"]
            
            # Clear LINE User ID from user profile
            supabase.table("users_local").update({
                "line_user_id": None
            }).eq("id", user_local_id).execute()
            
            # Disable all LINE notifications for this user
            supabase.table("tracking_subscriptions").update({
                "notify_line": False
            }).eq("user_id", user_local_id).execute()
            
            print(f"[LINE] Cleared LINE User ID and disabled notifications for user {user_local_id}")
        else:
            print(f"[LINE] No registered user found for LINE User ID {user_id}")
    
    except Exception as e:
        print(f"[LINE] Error handling unfollow event: {e}")
    
    except Exception as e:
        print(f"[LINE] Error handling unfollow event: {e}")


async def _handle_user_message(user_id: str, message_text: str):
    """
    Handle user sending a message to the bot.
    
    Examples:
    - "help": Show help message
    - "status": Show tracking status
    """
    print(f"[LINE] Message from {user_id}: {message_text}")
    
    from app.services.line_message_api import send_line_message
    
    message_lower = message_text.lower().strip()
    
    try:
        if message_lower == "help":
            help_text = (
                "📖 使用說明\n\n"
                "在應用中設置要追蹤的醫師和號碼，"
                "此機器人將自動在號碼接近時通知您。\n\n"
                "指令說明：\n"
                "• help - 顯示此說明\n"
                "• status - 查詢追蹤狀態\n"
            )
            await send_line_message(user_id, help_text)
        
        elif message_lower == "status":
            # Query user's tracking subscriptions
            supabase = get_supabase()
            
            # Find user by LINE User ID
            user_res = supabase.table("users_local").select("id").eq("line_user_id", user_id).execute()
            if not user_res.data:
                await send_line_message(user_id, "❌ 找不到您的帳號")
                return
            
            app_user_id = user_res.data[0]["id"]
            
            # Get active tracking subscriptions
            subs_res = supabase.table("tracking_subscriptions").select(
                "*, doctors(name), departments(name)"
            ).eq("user_id", app_user_id).eq("is_active", True).execute()
            
            if not subs_res.data:
                await send_line_message(user_id, "📭 您目前沒有啟用任何追蹤")
                return
            
            status_lines = ["📊 您的追蹤狀態：\n"]
            for sub in subs_res.data:
                doctor_name = (sub.get("doctors") or {}).get("name", "未知")
                dept_name = (sub.get("departments") or {}).get("name", "未知")
                session_date = sub.get("session_date", "未知")
                
                status_lines.append(
                    f"• {doctor_name} ({dept_name})\n"
                    f"  日期: {session_date}\n"
                )
            
            await send_line_message(user_id, "".join(status_lines))
        
        else:
            # Default reply for unknown commands
            reply = (
                "👋 感謝您的訊息！\n\n"
                "輸入 'help' 查看使用說明\n"
                "輸入 'status' 查詢追蹤狀態"
            )
            await send_line_message(user_id, reply)
    
    except Exception as e:
        print(f"[LINE] Error handling message: {e}")
        await send_line_message(user_id, "❌ 發生錯誤，請稍後再試")
