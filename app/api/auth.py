from fastapi import APIRouter, HTTPException, status, Depends
from app.database import get_supabase
from app.models.user import UserRegister, UserLogin, Token
from app.auth import get_password_hash, verify_password, create_access_token
from app.services.email_service import send_email
import os

router = APIRouter(prefix="/api/auth", tags=["Auth"])


@router.post("/register", status_code=201)
async def register(data: UserRegister):
    supabase = get_supabase()

    # 1. Check if user already exists
    existing = supabase.table("users_local").select("id").eq("email", data.email).execute()
    if existing.data:
        raise HTTPException(status_code=400, detail="此電子郵件已註冊")

    # 2. Hash password and prepare user record
    hashed_pwd = get_password_hash(data.password)
    import secrets
    v_token = secrets.token_urlsafe(32)

    user_payload = {
        "email": data.email,
        "hashed_password": hashed_pwd,
        "display_name": data.display_name or data.email.split("@")[0],
        "verification_token": v_token,
        "is_verified": False
    }
    
    # Add LINE identifiers if provided
    if data.line_user_id:
        user_payload["line_user_id"] = data.line_user_id
    if data.line_notify_token:
        user_payload["line_notify_token"] = data.line_notify_token

    try:
        res = supabase.table("users_local").insert(user_payload).execute()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not res.data:
        raise HTTPException(status_code=400, detail="註冊失敗")

    user_id = res.data[0]["id"]

    # 3. Send verification email via SMTP
    base_url = os.getenv("APP_BASE_URL", "http://localhost:8000")
    verify_link = f"{base_url}/api/auth/verify?token={v_token}"
    subject = "🏥 醫療門診追蹤系統 – 帳號驗證"
    body = f"""
    <h3>歡迎使用醫療門診追蹤系統！</h3>
    <p>請點擊下方連結以驗證您的帳號：</p>
    <p><a href="{verify_link}" style="padding:10px 20px; background:#1976D2; color:#fff; text-decoration:none; border-radius:5px;">驗證帳號</a></p>
    <p>若無法點擊，請複製連結：{verify_link}</p>
    """
    await send_email(data.email, subject, body)

    return {"message": "註冊成功！請檢查電子郵件以啟動帳號", "user_id": user_id}


from fastapi.responses import HTMLResponse

@router.get("/verify")
async def verify_email(token: str):
    supabase = get_supabase()
    res = supabase.table("users_local").select("*").eq("verification_token", token).execute()
    if not res.data:
        # Return a more friendly error page
        error_html = """
        <html>
            <head>
                <meta charset="utf-8">
                <title>驗證失敗</title>
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <style>
                    body { font-family: 'PingFang TC', 'Microsoft JhengHei', sans-serif; text-align: center; padding: 50px; background-color: #f4f7f6; }
                    .card { background: white; max-width: 400px; margin: 0 auto; padding: 30px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
                    .btn { display: inline-block; margin-top: 20px; padding: 12px 24px; background: #d32f2f; color: #fff; text-decoration: none; border-radius: 5px; font-weight: bold; }
                </style>
            </head>
            <body>
                <div class="card">
                    <h2 style="color: #d32f2f; margin-top: 0;">❌ 驗證代碼無效</h2>
                    <p style="color: #555; line-height: 1.5;">找不到此驗證連結或代碼已過期。請重新嘗試註冊，或聯繫支援人員。</p>
                    <a href="/" class="btn">回到首頁</a>
                </div>
            </body>
        </html>
        """
        return HTMLResponse(content=error_html, status_code=400)
    
    user_id = res.data[0]["id"]
    supabase.table("users_local").update({"is_verified": True, "verification_token": None}).eq("id", user_id).execute()
    
    html_content = """
    <html>
        <head>
            <meta charset="utf-8">
            <title>驗證成功</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                @keyframes scaleIn { from { transform: scale(0.8); opacity: 0; } to { transform: scale(1); opacity: 1; } }
                body { font-family: 'PingFang TC', 'Microsoft JhengHei', sans-serif; text-align: center; padding: 50px; background-color: #e3f2fd; }
                .card { background: white; max-width: 450px; margin: 0 auto; padding: 40px; border-radius: 16px; box-shadow: 0 10px 25px rgba(0,0,0,0.1); animation: scaleIn 0.5s ease-out; }
                .icon { font-size: 64px; color: #4caf50; margin-bottom: 20px; }
                h2 { color: #2c3e50; margin-top: 0; font-weight: 600; }
                p { color: #5d6d7e; line-height: 1.6; font-size: 16px; }
                .btn { display: inline-block; margin-top: 30px; padding: 14px 28px; background: #1976d2; color: #fff; text-decoration: none; border-radius: 8px; font-weight: bold; transition: background 0.3s; }
                .btn:hover { background: #1565c0; }
            </style>
        </head>
        <body>
            <div class="card">
                <div class="icon">✅</div>
                <h2>帳號驗證成功！</h2>
                <p>親愛的用戶，您的電子郵件信箱已驗證完畢。<br>現在您可以回到應用程式，開始追蹤您的醫療預約。</p>
                <a href="/" class="btn">前往登入頁面</a>
            </div>
        </body>
    </html>
    """
    return HTMLResponse(content=html_content, status_code=200, media_type="text/html; charset=utf-8")


@router.post("/login")
async def login(data: UserLogin):
    supabase = get_supabase()

    # 1. Fetch user by email
    res = supabase.table("users_local").select("*").eq("email", data.email).execute()
    if not res.data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="電子郵件或密碼錯誤",
        )

    user = res.data[0]

    # 2. Check password
    if not verify_password(data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="電子郵件或密碼錯誤",
        )

    # 3. Check if verified
    if not user.get("is_verified", False):
         raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="帳號尚未驗證，請至信箱點擊驗證連結",
        )

    # 4. Generate JWT + return profile to avoid extra /api/users/me round-trip
    access_token = create_access_token(data={"sub": str(user["id"])})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": str(user["id"]),
            "email": user.get("email"),
            "display_name": user.get("display_name"),
            "line_notify_token": user.get("line_notify_token"),
            "is_admin": user.get("is_admin", False),
            "is_verified": user.get("is_verified", False),
            "created_at": str(user.get("created_at", "")),
        }
    }


@router.post("/logout")
async def logout():
    return {"message": "已登出"}
