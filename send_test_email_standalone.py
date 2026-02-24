import asyncio
import os
import aiosmtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# Simple manual .env parser
def load_env(filepath=".env"):
    if not os.path.exists(filepath):
        return
    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                # Remove quotes if present
                if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                    value = value[1:-1]
                os.environ[key.strip()] = value.strip()

load_env()

async def send_email(to_email, subject, body_html):
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    # Handle potentially missing port
    try:
        smtp_port = int(os.getenv("SMTP_PORT", 587))
    except (TypeError, ValueError):
        smtp_port = 587
        
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    smtp_from = os.getenv("SMTP_FROM", "")
    smtp_from_name = os.getenv("SMTP_FROM_NAME", "醫療門診追蹤系統")

    if not smtp_user or not smtp_password:
        print(f"SMTP credentials missing. User: {smtp_user}, Pass: {'Set' if smtp_password else 'Not set'}")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{smtp_from_name} <{smtp_from}>"
    msg["To"] = to_email
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    try:
        await aiosmtplib.send(
            msg, hostname=smtp_host, port=smtp_port,
            username=smtp_user, password=smtp_password,
            start_tls=True
        )
        return True
    except Exception as e:
        print(f"SMTP Error: {e}")
        return False

def build_body(hospital_name, clinic_room, doctor_name, department_name, session_date, session_type, current_number, remaining, threshold):
    primary_color = "#1a73e8"
    accent_color = "#ea4335"
    secondary_color = "#5f6368"
    bg_color = "#f8f9fa"
    card_bg = "#ffffff"
    return f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="margin: 0; padding: 0; font-family: 'PingFang TC', 'Microsoft JhengHei', sans-serif; background-color: {bg_color};">
        <div style="max-width: 600px; margin: 20px auto; border-radius: 16px; overflow: hidden; background-color: {card_bg}; box-shadow: 0 4px 20px rgba(0,0,0,0.08);">
            <div style="background: linear-gradient(135deg, {primary_color} 0%, #1557b0 100%); padding: 30px; text-align: center;">
                <div style="font-size: 48px; margin-bottom: 10px;">🏥</div>
                <h1 style="color: #ffffff; margin: 0; font-size: 24px;">門診進度即時提醒 (測試)</h1>
            </div>
            <div style="padding: 30px; color: #3c4043;">
                <p style="color: {secondary_color};">親愛的用戶您好，系統偵測到您的關注門診已有新的進度：</p>
                <div style="background-color: {bg_color}; border-radius: 12px; padding: 24px; margin: 25px 0;">
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr><td style="padding: 8px 0; color: {secondary_color};">看診醫院</td><td style="text-align: right; font-weight: 600;">{hospital_name}</td></tr>
                        <tr><td style="padding: 8px 0; color: {secondary_color};">看診診間</td><td style="text-align: right; font-weight: 600;">{clinic_room}</td></tr>
                        <tr><td style="padding: 8px 0; color: {secondary_color};">看診醫師</td><td style="text-align: right; font-weight: 600;">{doctor_name} 醫師</td></tr>
                        <tr><td style="padding: 8px 0; color: {secondary_color};">門診科別</td><td style="text-align: right; font-weight: 600;">{department_name}</td></tr>
                        <tr><td style="padding: 8px 0; color: {secondary_color};">看診時段</td><td style="text-align: right; font-weight: 600;">{session_date} ({session_type})</td></tr>
                        <tr><td colspan="2" style="border-top:1px solid #dadce0; padding: 20px 0 10px 0;">
                            <table style="width:100%;"><tr>
                                <td style="width: 50%;"><div style="color:{secondary_color}; font-size: 13px;">目前號碼</div><div style="font-size:28px; font-weight: 700; color:{accent_color};">{current_number}</div></td>
                                <td style="width: 50%; text-align:right;"><div style="color:{secondary_color}; font-size: 13px;">距離您的號碼</div><div style="font-size:24px; font-weight: 700; color:{primary_color};">剩餘 {remaining} 位看診人數</div></td>
                            </tr></table>
                        </td></tr>
                    </table>
                </div>
                <div style="background-color: #fff8e1; border-left: 4px solid #ffb300; padding: 15px; border-radius: 4px; font-size: 14px; color: #856404; line-height: 1.5;">
                    💡 <strong>貼心叮嚀：</strong> 您設定的提醒門檻為「前 {threshold} 位看診人數」。目前的進度已進入您的預警範圍，建議您儘快前往候診區，以免錯過看診。
                </div>
            </div>
            <div style="padding: 24px; border-top: 1px solid #f1f3f4; text-align: center; color: #70757a; font-size: 12px;">
                © 2026 醫療門診追蹤系統 | 健康守護每一天
            </div>
        </div>
    </body>
    </html>
    """

async def main():
    target = "s254199tw@gmail.com"
    print(f"Sending final test email to {target}...")
    subject = "🔔 門診進度最終功能測試 (位看診人數)"
    body = build_body("臺中榮民總醫院", "診間 F", "林楨智", "骨科", "2026-02-24", "上午", 114, 5, 10)
    if await send_email(target, subject, body):
        print("Test Email Successfully Sent!")
    else:
        print("Test Email Sending Failed.")

if __name__ == "__main__":
    asyncio.run(main())
