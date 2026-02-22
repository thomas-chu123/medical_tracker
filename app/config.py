from pydantic_settings import BaseSettings
from pydantic import EmailStr
from functools import lru_cache


class Settings(BaseSettings):
    # Supabase
    supabase_url: str
    supabase_service_role_key: str
    supabase_anon_key: str

    # JWT
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440

    # SMTP Email
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_from_name: str = "醫療門診追蹤系統"

    # LINE Notify
    line_notify_token: str = ""

    # Scraper
    scrape_interval_minutes: int = 5
    request_timeout: int = 30

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()
