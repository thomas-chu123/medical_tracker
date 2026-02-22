from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class DepartmentData:
    name: str
    code: str
    hospital_code: str


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
    is_full: bool = False
    status: Optional[str] = None


@dataclass
class ClinicProgress:
    clinic_room: str
    session_type: str
    current_number: int
    status: Optional[str] = None


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
    async def fetch_clinic_progress(self, room: str, period: str) -> Optional[ClinicProgress]:
        ...
