
def build_clinic_alert_email(
    hospital_name: str,
    clinic_room: str,
    doctor_name: str,
    department_name: str,
    session_date: str,
    session_type: str,
    current_number: int,
    remaining: int,
    threshold: int,
) -> tuple[str, str]:
    """Build subject and HTML body for clinic alert with a premium design."""
    subject = f"🔔 門診進度提醒：{doctor_name} 醫師 (剩餘 {remaining} 位看診人數)"
    
    # Use a more vibrant and professional color palette
    primary_color = "#1a73e8"  # Google Blue
    accent_color = "#ea4335"   # Alert Red
    secondary_color = "#5f6368" # Text Gray
    bg_color = "#f8f9fa"
    card_bg = "#ffffff"

    body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
    </head>
    <body style="margin: 0; padding: 0; font-family: 'PingFang TC', 'Microsoft JhengHei', 'Helvetica Neue', Helvetica, Arial, sans-serif; background-color: {bg_color};">
        <div style="max-width: 600px; margin: 20px auto; padding: 0; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.08); background-color: {card_bg};">
            <!-- Header -->
            <div style="background: linear-gradient(135deg, {primary_color} 0%, #1557b0 100%); padding: 30px; text-align: center;">
                <div style="font-size: 48px; margin-bottom: 10px;">🏥</div>
                <h1 style="color: #ffffff; margin: 0; font-size: 24px; font-weight: 600; letter-spacing: 0.5px;">門診進度即時提醒</h1>
            </div>

            <!-- Content -->
            <div style="padding: 30px; color: #3c4043;">
                <p style="font-size: 16px; margin-top: 0; color: {secondary_color};">親愛的用戶您好，系統偵測到您的關注門診已有新的進度：</p>
                
                <div style="background-color: {bg_color}; border-radius: 12px; padding: 24px; margin: 25px 0;">
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 8px 0; color: {secondary_color}; font-size: 14px;">看診醫院</td>
                            <td style="padding: 8px 0; text-align: right; font-weight: 600; color: #202124;">{hospital_name}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: {secondary_color}; font-size: 14px;">看診診間</td>
                            <td style="padding: 8px 0; text-align: right; font-weight: 600; color: #202124;">{clinic_room}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: {secondary_color}; font-size: 14px;">看診醫師</td>
                            <td style="padding: 8px 0; text-align: right; font-weight: 600; color: #202124;">{doctor_name} 醫師</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: {secondary_color}; font-size: 14px;">門診科別</td>
                            <td style="padding: 8px 0; text-align: right; font-weight: 600; color: #202124;">{department_name}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: {secondary_color}; font-size: 14px;">看診時段</td>
                            <td style="padding: 8px 0; text-align: right; font-weight: 600; color: #202124;">{session_date} ({session_type})</td>
                        </tr>
                        <tr>
                            <td colspan="2" style="padding: 20px 0 10px 0; border-top: 1px solid #dadce0; margin-top: 10px;">
                                <table style="width: 100%;">
                                    <tr>
                                        <td style="width: 50%;">
                                            <div style="color: {secondary_color}; font-size: 13px; margin-bottom: 4px;">目前號碼</div>
                                            <div style="font-size: 28px; font-weight: 700; color: {accent_color};">{current_number}</div>
                                        </td>
                                        <td style="width: 50%; text-align: right;">
                                            <div style="color: {secondary_color}; font-size: 13px; margin-bottom: 4px;">距離您的號碼</div>
                                            <div style="font-size: 28px; font-weight: 700; color: {primary_color};">剩餘 {remaining} 位看診人數</div>
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>
                    </table>
                </div>

                <div style="background-color: #fff8e1; border-left: 4px solid #ffb300; padding: 15px; border-radius: 4px; font-size: 14px; color: #856404; line-height: 1.5;">
                    💡 <strong>貼心叮嚀：</strong> 您設定的提醒門檻為「前 {threshold} 位看診人數」。目前的進度已進入您的預警範圍，建議您儘快前往候診區，以免錯過看診。
                </div>

                <div style="margin-top: 30px; text-align: center;">
                    <a href="https://medical-tracker.thomas-chu.com" style="display: inline-block; padding: 14px 32px; background-color: {primary_color}; color: #ffffff; text-decoration: none; border-radius: 28px; font-weight: 600; font-size: 16px; box-shadow: 0 2px 5px rgba(26,115,232,0.3);">查看完整進度</a>
                </div>
            </div>

            <!-- Footer -->
            <div style="padding: 24px; border-top: 1px solid #f1f3f4; text-align: center; color: #70757a; font-size: 12px; line-height: 1.5;">
                <p style="margin: 0;">此信件為系統自動發送，請勿直接回覆。</p>
                <p style="margin: 8px 0 0 0;">© 2026 醫療門診追蹤系統 | 健康守護每一天</p>
            </div>
        </div>
    </body>
    </html>
    """
    return subject, body

with open("email_preview.html", "w", encoding="utf-8") as f:
    _, body = build_clinic_alert_email("臺中榮民總醫院", "診間 F", "林楨智", "骨科", "2026-02-24", "上午", 114, 5, 10)
    f.write(body)
