"""LINE Message API Webhook handler."""

import asyncio
import base64
import hashlib
import hmac
import json
from fastapi import APIRouter, Request, HTTPException
from app.config import get_settings
from app.database import get_supabase

import logging

settings = get_settings()
router = APIRouter(prefix="/api/webhooks", tags=["Webhooks"])
logger = logging.getLogger("medical_app")


@router.post("/line")
async def line_webhook(request: Request):
    """
    Handle LINE Message API webhook events.
    
    Webhook events:
    - follow: User adds the bot as a friend
    - unfollow: User removes the bot
    - message: User sends a message to the bot
    """

    # Get request body first
    body = await request.body()
    logger.info(f"[Webhook] POST /api/webhooks/line received, body={len(body)} bytes")

    # Log everything
    signature = request.headers.get("x-line-signature")
    print(f"\n{'='*60}")
    print(f"[LINE WEBHOOK] POST /api/webhooks/line received")
    print(f"[LINE WEBHOOK] Signature header present: {signature is not None}")
    if signature:
        print(f"[LINE WEBHOOK] Signature (first 20 chars): {signature[:20]}")
    print(f"[LINE WEBHOOK] Body length: {len(body)}")
    print(f"[LINE WEBHOOK] Body preview: {body[:200]}")
    print(f"{'='*60}\n")
    
    # Verify signature
    if not signature:
        logger.error("[Webhook] Missing X-LINE-Signature header")
        print("[LINE WEBHOOK] ERROR: Missing X-LINE-Signature header")
        raise HTTPException(status_code=403, detail="Missing X-LINE-Signature header")
    
    is_valid = _verify_signature(body, signature)
    logger.info(f"[Webhook] Signature valid: {is_valid}")
    print(f"[LINE WEBHOOK] Signature verification result: {is_valid}")
    
    if not is_valid:
        logger.error("[Webhook] Invalid signature - rejecting request")
        print("[LINE WEBHOOK] ERROR: Invalid signature - rejecting request")
        raise HTTPException(status_code=403, detail="Invalid signature")
    
    # Parse events
    data = json.loads(body)
    events = data.get('events', [])
    logger.info(f"[Webhook] Processing {len(events)} events")
    print(f"[LINE WEBHOOK] Processing {len(events)} events")
    
    for event in events:
        try:
            event_type = event.get("type")
            source_user = event.get("source", {}).get("userId", "unknown")
            logger.info(f"[Webhook] Event type={event_type} from userId={source_user}")
            if event_type == "follow":
                await _handle_user_follow(source_user)
            elif event_type == "unfollow":
                await _handle_user_unfollow(source_user)
            elif event_type == "message":
                msg_text = event["message"].get("text", "")
                logger.info(f"[Webhook] message text='{msg_text}'")
                await _handle_user_message(source_user, msg_text)
        except Exception as e:
            logger.error(f"[Webhook] Error processing event {event}: {e}", exc_info=True)
            print(f"[LINE Webhook] Error processing event: {e}")

    logger.info("[Webhook] Done processing all events")
    print("[LINE WEBHOOK] Response: OK")
    return {"status": "ok"}


def _verify_signature(body: bytes, signature: str) -> bool:
    """Verify LINE webhook signature."""
    print(f"\n[SIGNATURE VERIFY] Starting verification")
    print(f"[SIGNATURE VERIFY] Channel Secret configured: {bool(settings.line_channel_secret)}")
    
    if not settings.line_channel_secret:
        print("[SIGNATURE VERIFY] ERROR: No Channel Secret configured")
        return False
    
    print(f"[SIGNATURE VERIFY] Channel Secret (first 10): {settings.line_channel_secret[:10]}")
    
    hash_object = hmac.new(
        settings.line_channel_secret.encode('utf-8'),
        body,
        hashlib.sha256
    )
    expected_signature = base64.b64encode(hash_object.digest()).decode()
    
    print(f"[SIGNATURE VERIFY] Expected (first 20): {expected_signature[:20]}")
    print(f"[SIGNATURE VERIFY] Received (first 20): {signature[:20]}")
    
    match = signature == expected_signature
    print(f"[SIGNATURE VERIFY] Match: {match}")
    print(f"[SIGNATURE VERIFY] Expected length: {len(expected_signature)}, Received length: {len(signature)}")
    
    if not match:
        print(f"[SIGNATURE VERIFY] FULL Expected: {expected_signature}")
        print(f"[SIGNATURE VERIFY] FULL Received: {signature}")
    
    print()
    return match


async def _handle_user_follow(user_id: str):
    """
    Handle user following the bot.
    Just send a welcome message with bind instructions.
    Actual linking is done when user clicks 'Reconnect' in app settings.
    """
    logger.info(f"[Webhook] User {user_id} followed the bot")
    print(f"[LINE] User {user_id} followed the bot")

    try:
        from app.services.line_message_api import send_line_message
        await send_line_message(
            user_id,
            "歡迎使用台灣醫療門診追蹤系統！\n\n"
            "您已加入 LINE Bot。\n\n"
            "請在應用「個人設定 → LINE 通知設定」點擊「重新連結」按鈕，"
            "取得 6 位碼後在此輸入 bind XXXXXX 完成連結。"
        )
    except Exception as e:
        logger.error(f"[Webhook] Error handling follow event: {e}", exc_info=True)
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


async def _handle_user_message(user_id: str, message_text: str):
    """
    Handle user sending a message to the bot.

    Examples:
    - "help": Show help message
    - "status": Show tracking status
    - "綁定" or "link": For users already added the bot, trigger reconnect flow
    """
    print(f"[LINE] Message from {user_id}: {message_text}")
    
    from app.services.line_message_api import send_line_message
    
    message_lower = message_text.lower().strip()

    try:
        # Handle "bind CODE" command for users who are already friends
        if message_lower.startswith("bind ") or message_lower == "bind":
            from datetime import datetime, timezone

            logger.info(f"[Webhook][bind] Received bind command from LINE user {user_id}: '{message_text}'")

            supabase = get_supabase()

            # Extract code from message
            parts = message_text.strip().split()
            if len(parts) < 2:
                logger.warning(f"[Webhook][bind] No code provided by {user_id}")
                await send_line_message(
                    user_id,
                    "⚠️ 格式錯誤\n\n"
                    "請輸入：bind XXXXXX\n\n"
                    "(XXXXXX 是應用程式提供的 6 位碼)"
                )
                return

            temp_code = parts[1].strip().upper()   # normalize to uppercase
            logger.info(f"[Webhook][bind] Looking up temp_code='{temp_code}' for LINE user {user_id}")

            # Look up the code in line_pending_links
            try:
                pending_res = await asyncio.to_thread(
                    lambda: supabase.table("line_pending_links")
                        .select("id, user_id, temp_code, expires_at, line_user_id")
                        .eq("temp_code", temp_code)
                        .execute()
                )

                logger.info(f"[Webhook][bind] DB query result count={len(pending_res.data) if pending_res.data else 0}, data={pending_res.data}")

                if not pending_res.data:
                    logger.warning(f"[Webhook][bind] Code '{temp_code}' not found in line_pending_links")
                    await send_line_message(
                        user_id,
                        "❌ 碼不存在或已過期\n\n"
                        "請確認：\n"
                        "1. 碼是否正確（大小寫有別）\n"
                        "2. 是否已超過 10 分鐘\n"
                        "3. 是否已使用過\n\n"
                        "如需重新綁定，請在應用中重新申請。"
                    )
                    return

                pending_link = pending_res.data[0]
                expires_at_raw = pending_link["expires_at"]
                app_user_id = pending_link.get("user_id")
                logger.info(f"[Webhook][bind] Found pending link: id={pending_link['id']}, user_id={app_user_id}, expires_at={expires_at_raw}, already_linked={pending_link.get('line_user_id')}")

                # Check if already used (line_user_id is set = already consumed)
                if pending_link.get("line_user_id"):
                    logger.warning(f"[Webhook][bind] Code already used by LINE user {pending_link['line_user_id']}")
                    await send_line_message(user_id, "⚠️ 此碼已使用過，請在應用中重新申請新碼。")
                    return

                # Check if code has expired — use timezone-aware comparison
                if isinstance(expires_at_raw, str):
                    # Normalize: handle both '+00:00' and 'Z' suffix
                    expires_dt = datetime.fromisoformat(expires_at_raw.replace('Z', '+00:00'))
                else:
                    expires_dt = expires_at_raw

                now_utc = datetime.now(timezone.utc)
                logger.info(f"[Webhook][bind] Expiry check: now={now_utc.isoformat()}, expires={expires_dt.isoformat()}, expired={now_utc > expires_dt}")

                if now_utc > expires_dt:
                    logger.warning(f"[Webhook][bind] Code '{temp_code}' has expired")
                    await send_line_message(
                        user_id,
                        "⏰ 碼已過期\n\n"
                        "請在應用中重新申請新碼。"
                    )
                    return

                if not app_user_id:
                    logger.error(f"[Webhook][bind] pending link has no user_id! data={pending_link}")
                    await send_line_message(user_id, "❌ 綁定失敗：找不到對應的應用帳號，請重新申請。")
                    return

                # Code is valid — update users_local with this LINE User ID
                logger.info(f"[Webhook][bind] Code valid. Linking LINE user {user_id} → app user {app_user_id}")

                update_res = await asyncio.to_thread(
                    lambda: supabase.table("users_local")
                        .update({"line_user_id": user_id})
                        .eq("id", app_user_id)
                        .execute()
                )
                logger.info(f"[Webhook][bind] users_local update result: {update_res.data}")

                # Delete the pending link record (cleanup)
                await asyncio.to_thread(
                    lambda: supabase.table("line_pending_links")
                        .delete()
                        .eq("id", pending_link["id"])
                        .execute()
                )
                logger.info(f"[Webhook][bind] Pending link deleted. Binding complete.")

                await send_line_message(
                    user_id,
                    "✅ 重新連結成功！\n\n"
                    "您的帳號已成功重新連接 LINE Bot。\n"
                    "將來會透過此管道接收門診通知。"
                )
                return

            except Exception as e:
                logger.error(f"[Webhook][bind] Error processing bind code '{temp_code}': {e}", exc_info=True)
                await send_line_message(
                    user_id,
                    f"❌ 綁定失敗（伺服器錯誤）：{e}\n\n請稍後再試。"
                )
                return


        if message_lower == "help":
            help_text = (
                "📖 使用說明\n\n"
                "在應用中設置要追蹤的醫師和號碼，"
                "此機器人將自動在號碼接近時通知您。\n\n"
                "指令說明：\n"
                "• help - 顯示此說明\n"
                "• status - 查詢追蹤狀態\n"
                "• 綁定 - 如已加入 Bot 但帳號未連接，輸入此指令\n"
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
                "輸入 'status' 查詢追蹤狀態\n"
                "輸入 '綁定' 進行帳號連接"
            )
            await send_line_message(user_id, reply)
    
    except Exception as e:
        print(f"[LINE] Error handling message: {e}")
        await send_line_message(user_id, "❌ 發生錯誤，請稍後再試")
