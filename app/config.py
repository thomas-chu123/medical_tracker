from pydantic_settings import BaseSettings
from pydantic import EmailStr, ConfigDict
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

    # LINE Message API
    line_channel_access_token: str = ""
    line_channel_secret: str = ""

    # Scraper
    scrape_interval_minutes: int = 3
    request_timeout: int = 30

    # Notion Integration (Optional)
    notion_api: str = ""

    model_config = ConfigDict(env_file=".env", case_sensitive=False, extra="ignore")



@lru_cache()
def get_settings() -> Settings:
    return Settings()
