"""LINE Message API integration (replacing deprecated LINE Notify Bot)."""

import httpx
from app.config import get_settings

settings = get_settings()
LINE_MESSAGE_API_URL = "https://api.line.me/v2/bot/message/push"


async def send_line_message(user_id: str, message: str) -> dict:
    """
    Send a LINE message using Message API.
    
    Args:
        user_id: LINE User ID (from webhook events)
        message: Message text
    
    Returns:
        dict with keys: success (bool), http_status_code (int), error_message (str)
    """
    if not settings.line_channel_access_token:
        print("[LINE] No Channel Access Token configured, skipping.")
        return {
            "success": False,
            "http_status_code": None,
            "error_message": "No Channel Access Token configured"
        }
    
    if not user_id:
        print("[LINE] No user_id provided, skipping.")
        return {
            "success": False,
            "http_status_code": None,
            "error_message": "No user_id provided"
        }
    
    headers = {
        "Authorization": f"Bearer {settings.line_channel_access_token}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "to": user_id,
        "messages": [
            {
                "type": "text",
                "text": message
            }
        ]
    }
    
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.post(
                LINE_MESSAGE_API_URL,
                headers=headers,
                json=payload
            )
            success = resp.status_code == 200
            print(f"[LINE] Message sent {'OK' if success else 'FAILED'}: {resp.status_code}")
            
            if not success:
                error_text = resp.text
                print(f"[LINE] HTTP {resp.status_code}: {error_text}")
                print(f"[LINE] Debug - to: {user_id}, messages count: {len(payload.get('messages', []))}")
                return {
                    "success": False,
                    "http_status_code": resp.status_code,
                    "error_message": error_text[:500]  # Truncate long responses
                }
            
            return {
                "success": True,
                "http_status_code": 200,
                "error_message": None
            }
        except Exception as e:
            error_msg = str(e)
            print(f"[LINE] Exception: {error_msg}")
            print(f"[LINE] Debug - to: {user_id}, message length: {len(message)}")
            return {
                "success": False,
                "http_status_code": None,
                "error_message": error_msg
            }


def build_line_message(
    doctor_name: str,
    department_name: str,
    session_date: str,
    session_type: str,
    current_number: int,
    remaining: int,
    threshold: int,
    appointment_number: int | None = None,
    estimated_time: str | None = None,
) -> str:
    """Build a formatted LINE message."""
    appt_line = f"🎫 您的號碼：{appointment_number}\n" if appointment_number else ""
    est_time_line = f"⏱️ 預計看診時間：約 {estimated_time}\n" if estimated_time else ""
    return (
        f"\n⏰ 門診進度提醒\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👨‍⚕️ 醫師：{doctor_name}\n"
        f"🏥 科別：{department_name}\n"
        f"📅 日期：{session_date} {session_type}\n"
        f"📍 目前號碼：{current_number}\n"
        f"⚡ 距您還剩：{remaining} 人\n"
        f"{appt_line}"
        f"{est_time_line}"
        f"━━━━━━━━━━━━━━━\n"
        f"您設定的提醒門檻為前 {threshold} 號，請儘快前往候診！"
    )
