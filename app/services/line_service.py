"""LINE Notify integration."""

import httpx
from app.config import get_settings

settings = get_settings()
LINE_NOTIFY_URL = "https://notify-api.line.me/api/notify"


async def send_line_notify(token: str, message: str) -> bool:
    """Send a LINE Notify message. Returns True on success."""
    if not token:
        print("[LINE] No LINE Notify token configured, skipping.")
        return False

    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.post(
                LINE_NOTIFY_URL,
                headers=headers,
                data={"message": message},
            )
            success = resp.status_code == 200
            print(f"[LINE] Send {'OK' if success else 'FAILED'}: {resp.status_code}")
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
    hospital_name: str | None = None,
    clinic_room: str | None = None,
) -> str:
    hospital_line = f"🏛️ 醫院：{hospital_name}\n" if hospital_name else ""
    clinic_room_line = f"🚪 診間：{clinic_room}\n" if clinic_room else ""
    return (
        f"\n⏰ 門診進度提醒\n"
        f"━━━━━━━━\n"
        f"{hospital_line}"
        f"👨‍⚕️ 醫師：{doctor_name}\n"
        f"🏥 科別：{department_name}\n"
        f"📅 日期：{session_date} {session_type}\n"
        f"{clinic_room_line}"
        f"📍 目前號碼：{current_number}\n"
        f"⚡ 距您還剩：{remaining} 號\n"
        f"━━━━━━━━\n"
        f"您設定的提醒門檻為前 {threshold} 號，請儘快前往候診！"
    )
