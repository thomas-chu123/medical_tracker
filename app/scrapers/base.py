from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Optional


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
