from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import EmailStr, field_validator, Field
from functools import lru_cache
from typing import List


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
    # 啟用的醫院爬蟲列表（逗號分隔字符串）
    # 預設值支持中榮台中院和中榮新竹院
    # 支援的醫院代碼（以逗號分隔）
    # 目前支援：
    #   - CMUH_TAICHUNG: 中國醫藥大學附設醫院（台中總院）
    #   - CMUH_HSINCHU: 中北醫藥大學新竹附設醫院（新竹分院）
    #   - NTUH_HSINCHU: 台大醫院新竹分院
    #   - HMMH: 馬偕紀念醫院新竹分院
    #   - TVGH_HSINCHU: 臺北榮民總醫院新竹分院
    # 範例：在 .env 中設為 "CMUH_TAICHUNG,CMUH_HSINCHU,NTUH_HSINCHU,HMMH,TVGH_HSINCHU"
    enabled_hospitals_str: str = Field(
        default="CMUH_TAICHUNG,CMUH_HSINCHU,NTUH_HSINCHU,HMMH,TVGH_HSINCHU,TYGH_HSINCHU,TVGH_TAICHUNG",
        validation_alias="ENABLED_HOSPITALS"  # 允許 ENABLED_HOSPITALS 環境變數對應此字段
    )

    # Notion Integration (Optional)
    notion_api: str = ""

    # App URL
    app_base_url: str = "http://localhost:8000"

    # Debug
    debug: int = Field(default=0, description="Enable debug logging (1 or 0)")

    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding='utf-8',
        case_sensitive=False, 
        extra="ignore",
        populate_by_name=True  # 支持別名
    )

    @field_validator("enabled_hospitals_str", mode="after")
    @classmethod
    def parse_enabled_hospitals_str(cls, v):
        """驗證並轉換逗號分隔的醫院列表字符串"""
        if not v:
            return "CMUH_TAICHUNG,CMUH_HSINCHU"
        return v

    @property
    def enabled_hospitals(self) -> List[str]:
        """解析醫院列表（屬性形式）"""
        return [h.strip() for h in self.enabled_hospitals_str.split(",") if h.strip()]



@lru_cache()
def get_settings() -> Settings:
    return Settings()
