import asyncio
import os
import sys

# Ensure app module can be found
sys.path.append(os.getcwd())

from app.database import get_supabase
from app.services.email_service import build_clinic_alert_email, send_email
from app.services.notification import _get_user_email

async def main():
    supabase = get_supabase()
    # The user ID found in tracking_subscriptions
    user_id = "ef488308-b6af-479b-824a-9a02c55527bf"
    email = await _get_user_email(supabase, user_id)
    
    if not email:
        print(f"Could not find email for user {user_id}")
        return

    print(f"Targeting email: {email}")

    subject, body = build_clinic_alert_email(
        hospital_name="中國醫藥大學附設醫院 (測試)",
        clinic_room="J117 (測試)",
        doctor_name="林楨智 (測試)",
        department_name="骨科 (測試)",
        session_date="2026-02-24",
        session_type="上午",
        current_number=114,
        remaining=5,
        threshold=10
    )
    
    success = await send_email(email, subject, body)
    if success:
        print(f"Test email successfully sent to {email}")
    else:
        print(f"Failed to send test email to {email}")

if __name__ == "__main__":
    asyncio.run(main())
