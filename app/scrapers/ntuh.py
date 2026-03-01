"""
NTUH Hsinchu (國立臺灣大學醫學院附設醫院新竹分院) Scraper

Scrapes appointment data from NTUH Hsinchu (新竹臺大分院).

APIs:
1. RegShowBlock?vHospCode=T4 → department list + form for fetching doctor schedules
2. ClinicCurrentLightNo?vHospCode=T4 → current queue number query form

Data flow:
- fetch_departments(): Extract department list from RegShowBlock HTML
- fetch_schedule(dept_code): POST form to RegShowBlock, parse doctor schedule table
- fetch_clinic_progress(room, period): POST form to ClinicCurrentLightNo, extract current number
"""

import asyncio
import re
from datetime import date
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.logger import logger as log
from app.core.timezone import now_tw, today_tw_str
from app.scrapers.base import BaseScraper, DepartmentData, DoctorSlot, ClinicProgress
from app.config import get_settings

settings = get_settings()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://reg.ntuh.gov.tw/",
}

# Period mapping: NTUH uses numeric codes (1=上午, 2=下午, 3=晚上)
PERIOD_MAP = {
    "1": "上午",
    "2": "下午", 
    "3": "晚上",
}

# Reverse mapping for converting to numeric codes
PERIOD_REVERSE_MAP = {
    "上午": "1",
    "下午": "2",
    "晚上": "3",
}


def _parse_int(text: Optional[str]) -> Optional[int]:
    """Extract first integer from a string."""
    if not text:
        return None
    m = re.search(r"\d+", text.strip())
    return int(m.group()) if m else None


class NTUHHsinchuScraper(BaseScraper):
    """
    Scraper for NTUH Hsinchu (國立臺灣大學醫學院附設醫院新竹分院).
    
    Hospital Code: NTUH_HSINCHU
    API Code: T4
    """

    HOSPITAL_CODE = "NTUH_HSINCHU"
    BASE_URL = "https://reg.ntuh.gov.tw/WebReg/WebReg"

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=HEADERS,
                timeout=settings.request_timeout,
                follow_redirects=True,
            )
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _get(self, url: str, **kwargs) -> str:
        """Execute GET request with retry logic."""
        log.info(f"[NTUH] GET {url} with params {kwargs.get('params')}")
        client = await self._get_client()
        resp = await client.get(url, **kwargs)
        resp.raise_for_status()
        log.info(f"[NTUH] GET {url} success ({len(resp.text)} chars)")
        return resp.text

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _post(self, url: str, data: dict) -> str:
        """Execute POST request with retry logic."""
        log.info(f"[NTUH] POST {url} with data keys {list(data.keys())}")
        client = await self._get_client()
        resp = await client.post(url, data=data)
        resp.raise_for_status()
        log.info(f"[NTUH] POST {url} success ({len(resp.text)} chars)")
        return resp.text

    # ─────────────────────────────────────────────────────────
    # 1. Fetch department list
    # ─────────────────────────────────────────────────────────
    async def fetch_departments(self) -> list[DepartmentData]:
        """
        Fetch department list from NTUH Hsinchu.
        
        Returns:
            list[DepartmentData]: List of departments with code, name, and hospital code.
        """
        url = f"{self.BASE_URL}/RegShowBlock"
        html = await self._get(url, params={"vHospCode": "T4"})
        soup = BeautifulSoup(html, "html.parser")

        departments: list[DepartmentData] = []

        # Find the department select dropdown (selectedVDeptCode)
        select = soup.find("select", id="selectedVDeptCode")
        if not select:
            log.warning("[NTUH] Could not find department select dropdown")
            return []

        # Extract options (skip the first "搜尋全部科部" option)
        sort_order = 1
        for option in select.find_all("option"):
            code = option.get("value", "").strip()
            name = option.get_text(strip=True)

            # Skip empty or placeholder options
            if not code or code == "" or "搜尋" in name:
                continue

            departments.append(
                DepartmentData(
                    name=name,
                    code=code,
                    hospital_code=self.HOSPITAL_CODE,
                    sort_order=sort_order,
                )
            )
            sort_order += 1

        log.info(f"[NTUH] Fetched {len(departments)} departments")
        return departments

    # ─────────────────────────────────────────────────────────
    # 2. Fetch doctor slots for a department
    # ─────────────────────────────────────────────────────────
    async def fetch_schedule(self, dept_code: str) -> list[DoctorSlot]:
        """
        Fetch doctor schedule for a specific department.
        
        Args:
            dept_code: Department code (e.g., "MED", "SURG")
            
        Returns:
            list[DoctorSlot]: List of doctor slots with doctor info and schedule.
        """
        log.info(f"[NTUH] fetch_schedule for department {dept_code}")
        
        # First, fetch the main page to get verification tokens and form data
        url = f"{self.BASE_URL}/RegShowBlock"
        html = await self._get(url, params={"vHospCode": "T4"})
        soup = BeautifulSoup(html, "html.parser")

        # Extract verification token and other hidden form fields
        form_data = {}
        for hidden_input in soup.find_all("input", type="hidden"):
            name = hidden_input.get("name", "")
            value = hidden_input.get("value", "")
            if name:
                form_data[name] = value

        # Add department selection to form
        form_data["selectedVDeptCode"] = dept_code

        # POST to get the schedule table
        html = await self._post(url, form_data)
        soup = BeautifulSoup(html, "html.parser")

        slots: list[DoctorSlot] = []
        today = date.today()

        # Parse the schedule table
        # NTUH typically displays schedule as a table with doctor names and time slots
        tables = soup.find_all("table")
        
        if not tables:
            log.warning(f"[NTUH] No schedule table found for department {dept_code}")
            return []

        # Look for doctor rows in the schedule table
        # The structure may vary, so we'll look for common patterns
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all(["td", "th"])
                if len(cells) < 3:
                    continue

                # Try to extract doctor name, session type, quota, etc.
                # Structure varies, but typically:
                # Col 0: Doctor name
                # Col 1: Session type (上午/下午/晚上)
                # Col 2+: Dates and quotas

                try:
                    doctor_name = cells[0].get_text(strip=True)
                    session_text = cells[1].get_text(strip=True) if len(cells) > 1 else ""
                    
                    # Parse session type
                    session_type = session_text
                    if session_type not in PERIOD_MAP.values():
                        continue

                    # Extract quota and registered count if present
                    quota_text = cells[2].get_text(strip=True) if len(cells) > 2 else ""
                    total_quota = _parse_int(quota_text)
                    registered = None

                    # Extract clinic room if present
                    clinic_room = None
                    if len(cells) > 3:
                        room_text = cells[3].get_text(strip=True)
                        # Look for patterns like "5診" or "診間5"
                        m = re.search(r"(\d+)\s*診", room_text)
                        if m:
                            clinic_room = m.group(1)

                    # Generate a unique doctor number if not available
                    doctor_no = re.sub(r"[^\w]", "", doctor_name)[:10]

                    slots.append(
                        DoctorSlot(
                            doctor_no=doctor_no,
                            doctor_name=doctor_name,
                            department_code=dept_code,
                            session_date=today,
                            session_type=session_type,
                            total_quota=total_quota,
                            registered=registered,
                            clinic_room=clinic_room,
                        )
                    )
                except (IndexError, ValueError) as e:
                    log.debug(f"[NTUH] Error parsing row: {e}")
                    continue

        log.info(f"[NTUH] Fetched {len(slots)} doctor slots for department {dept_code}")
        return slots

    # ─────────────────────────────────────────────────────────
    # 3. Fetch clinic progress (current queue number)
    # ─────────────────────────────────────────────────────────
    async def fetch_clinic_progress(self, room: str, period: str) -> Optional[ClinicProgress]:
        """
        Fetch current clinic progress (queue number) for a clinic room and session.
        
        Args:
            room: Clinic room number (e.g., "1", "5", "10")
            period: Session period code ("1" for 上午, "2" for 下午, "3" for 晚上)
            
        Returns:
            Optional[ClinicProgress]: Current clinic progress or None if not available.
        """
        log.info(f"[NTUH] fetch_clinic_progress for room {room}, period {period}")
        
        # Fetch the clinic progress query form
        url = f"{self.BASE_URL}/ClinicCurrentLightNo"
        html = await self._get(url, params={"vHospCode": "T4"})
        soup = BeautifulSoup(html, "html.parser")

        # Extract verification token and form data
        form_data = {}
        for hidden_input in soup.find_all("input", type="hidden"):
            name = hidden_input.get("name", "")
            value = hidden_input.get("value", "")
            if name:
                form_data[name] = value

        # Add search parameters
        form_data["DropListHosp"] = "T4"  # NTUH Hsinchu
        form_data["DropDownDept"] = ""  # Will be set if specific department is needed
        form_data["DropListRegion"] = ""  # Region selection
        form_data["ClinicRoom"] = room
        form_data["Period"] = period

        # POST to get the current progress
        html = await self._post(url, form_data)
        soup = BeautifulSoup(html, "html.parser")

        # Parse the response to find current queue number
        # Look for display elements showing "目前號碼" or similar
        progress_elements = soup.find_all(string=re.compile(r"目前|號碼|診號"))
        
        current_number = None
        for elem in progress_elements:
            # Look for numeric patterns near the text
            parent = elem.parent
            if parent:
                text = parent.get_text(strip=True)
                m = re.search(r"(\d+)", text)
                if m:
                    current_number = int(m.group(1))
                    break

        if current_number is not None:
            session_type_name = PERIOD_MAP.get(period, period)
            return ClinicProgress(
                clinic_room=room,
                session_type=session_type_name,
                current_number=current_number,
                total_quota=None,
                registered_count=None,
                status=None,
                waiting_list=[],
                clinic_queue_details=[],
            )

        log.debug(f"[NTUH] No clinic progress data found for room {room}, period {period}")
        return None
