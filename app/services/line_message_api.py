"""LINE Message API integration (replacing deprecated LINE Notify Bot)."""

import httpx
from app.config import get_settings

settings = get_settings()
LINE_MESSAGE_API_URL = "https://api.line.me/v2/bot/message/push"


async def send_line_message(user_id: str, message: str) -> bool:
    """
    Send a LINE message using Message API.
    
    Args:
        user_id: LINE User ID (from webhook events)
        message: Message text
    
    Returns:
        True if successful, False otherwise
    """
    if not settings.line_channel_access_token:
        print("[LINE] No Channel Access Token configured, skipping.")
        return False
    
    if not user_id:
        print("[LINE] No user_id provided, skipping.")
        return False
    
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
                print(f"[LINE] Response: {resp.text}")
            return success
        except Exception as e:
            print(f"[LINE] Error: {e}")
            return False


def build_line_message(
    doctor_name: str,
    department_name: str,
    session_date: str,
    session_type: str,
    current_number: int,
    remaining: int,
    threshold: int,
) -> str:
    """Build a formatted LINE message."""
    return (
        f"\n⏰ 門診進度提醒\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👨‍⚕️ 醫師：{doctor_name}\n"
        f"🏥 科別：{department_name}\n"
        f"📅 日期：{session_date} {session_type}\n"
        f"📍 目前號碼：{current_number}\n"
        f"⚡ 距您還剩：{remaining} 人\n"
        f"━━━━━━━━━━━━━━━\n"
        f"您設定的提醒門檻為前 {threshold} 號，請儘快前往候診！"
    )
