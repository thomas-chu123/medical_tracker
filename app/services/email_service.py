"""Email notification service using aiosmtplib (SMTP)."""

import aiosmtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import get_settings

settings = get_settings()


async def send_email(
    to_email: str,
    subject: str,
    body_html: str,
) -> bool:
    """Send an HTML email. Returns True on success."""
    if not settings.smtp_user or not settings.smtp_password:
        print("[Email] SMTP credentials not configured, skipping.")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from}>"
    msg["To"] = to_email
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user,
            password=settings.smtp_password,
            start_tls=True,
        )
        print(f"[Email] Sent to {to_email}: {subject}")
        return True
    except Exception as e:
        print(f"[Email] Failed to send to {to_email}: {e}")
        return False


def build_clinic_alert_email(
    doctor_name: str,
    department_name: str,
    session_date: str,
    session_type: str,
    current_number: int,
    remaining: int,
    threshold: int,
) -> tuple[str, str]:
    """Build subject and HTML body for clinic alert."""
    subject = f"⏰ 門診提醒：{doctor_name} 醫師 – 還剩 {remaining} 號！"
    body = f"""
    <html><body style="font-family: Arial, sans-serif; color: #333;">
    <div style="max-width:480px; margin:0 auto; padding:24px;
                border:1px solid #e0e0e0; border-radius:12px;">
        <h2 style="color:#1976D2;">🏥 門診進度提醒</h2>
        <table style="width:100%; border-collapse:collapse;">
        <tr><td style="padding:6px 0; color:#666;">醫師</td>
            <td style="padding:6px 0; font-weight:bold;">{doctor_name}</td></tr>
        <tr><td style="padding:6px 0; color:#666;">科別</td>
            <td style="padding:6px 0;">{department_name}</td></tr>
        <tr><td style="padding:6px 0; color:#666;">日期</td>
            <td style="padding:6px 0;">{session_date} {session_type}</td></tr>
        <tr><td style="padding:6px 0; color:#666;">目前號碼</td>
            <td style="padding:6px 0; font-size:24px; font-weight:bold;
                        color:#E53935;">{current_number}</td></tr>
        <tr><td style="padding:6px 0; color:#666;">距您還剩</td>
            <td style="padding:6px 0; font-size:20px; font-weight:bold;
                        color:#F57C00;">{remaining} 號</td></tr>
        </table>
        <p style="margin-top:20px; padding:12px; background:#FFF3E0;
                   border-radius:8px; font-size:14px;">
            📍 您設定的提醒門檻為 <strong>前 {threshold} 號</strong>，
            請儘快前往醫院候診！
        </p>
        <p style="font-size:12px; color:#aaa; margin-top:16px;">
            此為系統自動通知，請勿直接回覆。
        </p>
    </div>
    </body></html>
    """
    return subject, body
