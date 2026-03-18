from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)


# ───────────────────────────────────────────────────────────────
# 自訂異常類別
# ───────────────────────────────────────────────────────────────
class ScraperException(Exception):
    """所有 Scraper 異常的基礎類別"""
    pass


class ScraperNetworkError(ScraperException):
    """網路連接失敗（RemoteProtocolError, ConnectError 等）"""
    pass


class ScraperTimeoutError(ScraperException):
    """HTTP 請求逾時"""
    pass


class ScraperParseError(ScraperException):
    """HTML 解析失敗"""
    pass


class ScraperHTTPError(ScraperException):
    """HTTP 狀態碼異常（4xx, 5xx）"""
    pass


# ───────────────────────────────────────────────────────────────
# 重試策略：針對網路異常的指數退避重試
# ───────────────────────────────────────────────────────────────
def _is_retryable_error(exc: Exception) -> bool:
    """判斷異常是否應該重試。"""
    if isinstance(exc, (
        httpx.RemoteProtocolError,
        httpx.ConnectError,
        httpx.TimeoutException,
        httpx.ProxyError,
        httpx.NetworkError,
    )):
        return True
    if isinstance(exc, ScraperNetworkError):
        return True
    return False


RETRY_DECORATOR = retry(
    stop=stop_after_attempt(5),  # 最多重試 5 次
    wait=wait_exponential(multiplier=1, min=2, max=30),  # 2^n 秒，最多 30 秒
    retry=retry_if_exception_type((
        httpx.RemoteProtocolError,
        httpx.ConnectError,
        httpx.TimeoutException,
        httpx.ProxyError,
        httpx.NetworkError,
        ScraperNetworkError,
    )),
    reraise=True,  # 最終失敗時重新拋出異常
)


@dataclass
class DepartmentData:
    name: str
    code: str
    hospital_code: str
    category: Optional[str] = None
    sort_order: int = 0


@dataclass
class DoctorSlot:
    doctor_no: str
    doctor_name: str
    department_code: str
    session_date: date
    session_type: str           # '上午' / '下午' / '晚上'
    total_quota: Optional[int]
    registered: Optional[int]
    clinic_room: Optional[str]
    current_number: Optional[int] = None
    is_full: bool = False
    status: Optional[str] = None
    internal_dept_code: Optional[str] = None  # HMMH: internal depid for register_single_doctor.php


@dataclass
class ClinicProgress:
    clinic_room: str
    session_type: str
    current_number: int
    total_quota: Optional[int] = None
    registered_count: Optional[int] = None
    status: Optional[str] = None
    waiting_list: list[int] = field(default_factory=list)
    clinic_queue_details: list[dict] = field(default_factory=list)  # [{"number": 1, "status": "完成"}, ...]


class BaseScraper(ABC):
    HOSPITAL_CODE: str = ""
    BASE_URL: str = ""

    @abstractmethod
    async def fetch_departments(self) -> list[DepartmentData]:
        ...

    @abstractmethod
    async def fetch_schedule(self, dept_code: str) -> list[DoctorSlot]:
        ...

    @abstractmethod
    async def fetch_clinic_progress(self, room: str, period: str, **kwargs) -> Optional[ClinicProgress]:
        ...

    @abstractmethod
    def calculate_remaining_count(
        self,
        current_number: int,
        target_number: int,
        clinic_queue_details: list[dict],
    ) -> int:
        """
        計算從當前號碼到目標號碼之間還有多少人未看診。
        
        各醫院的邏輯可能不同，例如：
        - CMUH：排除狀態為"完成"的號碼
        - NTUH：統計所有號碼（不過濾特定狀態）
        
        Args:
            current_number: 目前正在看診的號碼
            target_number: 使用者的掛號號碼
            clinic_queue_details: 燈號清單，格式為 [{"number": 1, "status": "完成"}, ...]
        
        Returns:
            還剩多少人未看診的數量
        """
        ...
