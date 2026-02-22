"""
CMUH (中國醫藥大學附設醫院) Scraper

Scrapes:
1. /OnlineAppointment/AppointmentByDivision?flag=first  → department list
2. /OnlineAppointment/DymSchedule?table={code}&flag=first → doctor schedules
3. /OnlineAppointment/DoctorInfo?DocNo={no}             → appointment counts
4. /OnlineAppointment/ClinicQuery                       → current queue number
"""

import asyncio
import re
from datetime import date, datetime
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

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
    "Referer": "https://www.cmuh.cmu.edu.tw/",
}


def _parse_int(text: Optional[str]) -> Optional[int]:
    """Extract first integer from a string."""
    if not text:
        return None
    m = re.search(r"\d+", text.strip())
    return int(m.group()) if m else None


class CMUHScraper(BaseScraper):
    HOSPITAL_CODE = "CMUH"
    BASE_URL = "https://www.cmuh.cmu.edu.tw"

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=HEADERS,
                timeout=settings.request_timeout,
                follow_redirects=True,
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _get(self, url: str, **kwargs) -> str:
        client = await self._get_client()
        resp = await client.get(url, **kwargs)
        resp.raise_for_status()
        return resp.text

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _post(self, url: str, data: dict) -> str:
        client = await self._get_client()
        resp = await client.post(url, data=data)
        resp.raise_for_status()
        return resp.text

    # ─────────────────────────────────────────────────────────
    # 1. Fetch department list
    # ─────────────────────────────────────────────────────────
    async def fetch_departments(self) -> list[DepartmentData]:
        url = f"{self.BASE_URL}/OnlineAppointment/AppointmentByDivision"
        html = await self._get(url, params={"flag": "first"})
        soup = BeautifulSoup(html, "lxml")

        departments: list[DepartmentData] = []

        # Links that look like DymSchedule?table=XXXXX
        for a in soup.find_all("a", href=True):
            href = a["href"]
            m = re.search(r"table=([A-Za-z0-9]+)", href)
            if m:
                code = m.group(1)
                name = a.get_text(strip=True)
                if name:
                    departments.append(
                        DepartmentData(
                            name=name,
                            code=code,
                            hospital_code=self.HOSPITAL_CODE,
                        )
                    )

        # Deduplicate by code
        seen = set()
        unique: list[DepartmentData] = []
        for d in departments:
            if d.code not in seen:
                seen.add(d.code)
                unique.append(d)
        return unique

    # ─────────────────────────────────────────────────────────
    # 2. Fetch doctor slots for a department
    # ─────────────────────────────────────────────────────────
    async def fetch_schedule(self, dept_code: str) -> list[DoctorSlot]:
        url = f"{self.BASE_URL}/OnlineAppointment/DymSchedule"
        html = await self._get(url, params={"table": dept_code, "flag": "first"})
        soup = BeautifulSoup(html, "lxml")

        slots: list[DoctorSlot] = []
        today = date.today()

        # The schedule is rendered as a table/div grid
        # Each row typically has: doctor name, date, session type, quota, registered, status
        # We'll look for all doctor links first, then scrape doctor details
        doctor_links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            m = re.search(r"DocNo=([A-Za-z0-9]+)", href)
            if m:
                doc_no = m.group(1)
                doc_name = a.get_text(strip=True)
                if doc_name and doc_no not in [d[0] for d in doctor_links]:
                    doctor_links.append((doc_no, doc_name))

        # Fetch details for all doctors concurrently (limit concurrency)
        sem = asyncio.Semaphore(5)

        async def fetch_one(doc_no: str, doc_name: str):
            async with sem:
                return await self._fetch_doctor_slots(doc_no, doc_name, dept_code)

        results = await asyncio.gather(
            *[fetch_one(no, name) for no, name in doctor_links],
            return_exceptions=True,
        )
        for r in results:
            if isinstance(r, list):
                slots.extend(r)
        return slots

    # ─────────────────────────────────────────────────────────
    # 3. Fetch individual doctor appointment details
    # ─────────────────────────────────────────────────────────
    async def _fetch_doctor_slots(
        self, doc_no: str, doc_name: str, dept_code: str
    ) -> list[DoctorSlot]:
        # The doctor info page on the main site is just a shell.
        # The actual schedule is in an iframe pointing to the appointment backend.
        # Doctor IDs in the appointment backend need a 'D' prefix.
        appointment_doc_no = f"D{doc_no}" if not doc_no.startswith("D") else doc_no
        url = "https://appointment.cmuh.org.tw/cgi-bin/reg52.cgi"
        
        client = await self._get_client()
        try:
            # Need to handle Big5/CP950 encoding from the CGI backend
            resp = await client.get(url, params={"DocNo": appointment_doc_no, "Docname": doc_name})
            resp.raise_for_status()
            html = resp.content.decode("big5", errors="ignore")
        except Exception as e:
            print(f"Error fetching doctor info for {doc_no}: {e}")
            return []

        soup = BeautifulSoup(html, "lxml")
        slots: list[DoctorSlot] = []

        # The CGI backend returns a table where each row's first cell is the session time.
        # The other cells (columns 2-8) correspond to days of the week.
        # Each cell (schBox) can contain multiple date blocks if the doctor has multiple clinics.
        # Example: 115/02/23已掛號：58 人(230診)115/03/02...
        rows = soup.find_all("tr")
        for row in rows:
            cells = row.find_all(["td", "th"])
            if not cells:
                continue

            session_text = cells[0].get_text(strip=True)
            session_type = self._normalize_session_type(session_text)
            
            # Skip rows that aren't session rows (e.g. header rows)
            if session_type == session_text and not any(s in session_text for s in ["上午", "下午", "晚上"]):
                continue

            # Iterate through columns (days of the week)
            for cell in cells[1:]:
                text = cell.get_text(strip=True)
                if not text:
                    continue

                # Use regex to find all date blocks in the cell
                # Pattern: ROC date (11x/xx/xx) followed by optional registration/room info
                # We split the cell text by the date pattern
                matches = list(re.finditer(r"(\d{3}/\d{2}/\d{2})", text))
                if not matches:
                    continue

                # Add a dummy end position to handle the last block
                positions = [m.start() for m in matches]
                positions.append(len(text))

                for i in range(len(matches)):
                    block = text[positions[i] : positions[i + 1]]
                    
                    # Parse block details
                    d_str = matches[i].group(1)
                    session_date = self._parse_date(d_str)
                    if not session_date:
                        continue

                    registered = _parse_int(re.search(r"已掛號：(\d+)", block).group(1)) if re.search(r"已掛號：(\d+)", block) else None
                    room_match = re.search(r"\((\d+診)\)", block)
                    clinic_room = room_match.group(1) if room_match else None
                    is_full = "額滿" in block or "掛滿" in block
                    status_text = "額滿" if is_full else None

                    slots.append(
                        DoctorSlot(
                            doctor_no=doc_no,
                            doctor_name=doc_name,
                            department_code=dept_code,
                            session_date=session_date,
                            session_type=session_type,
                            total_quota=None,           # CGI doesn't easily show quota
                            registered=registered,
                            clinic_room=clinic_room,
                            is_full=is_full,
                            status=status_text,
                        )
                    )
        return slots

    # ─────────────────────────────────────────────────────────
    # 4. Fetch clinic queue progress
    # ─────────────────────────────────────────────────────────
    async def fetch_clinic_progress(
        self, room: str, period: str
    ) -> Optional[ClinicProgress]:
        """
        Query current calling number.
        period: '1'=morning, '2'=afternoon, '3'=evening
        """
        url = f"{self.BASE_URL}/OnlineAppointment/ClinicQuery"
        try:
            html = await self._post(url, data={"ClinicRoom": room, "TimePeriod": period})
        except Exception:
            return None

        soup = BeautifulSoup(html, "lxml")

        # Look for the current number in the response
        current_number = None
        for tag in soup.find_all(text=True):
            m = re.search(r"目前看診號[：:]\s*(\d+)", tag)
            if m:
                current_number = int(m.group(1))
                break
            m = re.search(r"(\d+)\s*號", tag)
            if m and current_number is None:
                current_number = int(m.group(1))

        if current_number is None:
            # Try to extract any number from inside a result element
            result_div = soup.find(class_=re.compile(r"result|number|current", re.I))
            if result_div:
                current_number = _parse_int(result_div.get_text())

        if current_number is None:
            return None

        period_map = {"1": "上午", "2": "下午", "3": "晚上"}
        return ClinicProgress(
            clinic_room=room,
            session_type=period_map.get(period, period),
            current_number=current_number,
        )

    # ─────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────
    @staticmethod
    def _parse_date(text: str) -> Optional[date]:
        text = text.strip()
        # Support formats: 2024/01/15, 2024-01-15, 113/01/15 (ROC year)
        patterns = [
            (r"(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})", False),  # AD year
            (r"(\d{3})[/\-](\d{1,2})[/\-](\d{1,2})", True),   # ROC year
        ]
        for pat, is_roc in patterns:
            m = re.search(pat, text)
            if m:
                y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if is_roc:
                    y += 1911
                try:
                    return date(y, mo, d)
                except ValueError:
                    continue
        return None

    @staticmethod
    def _normalize_session_type(text: str) -> str:
        if "上午" in text or "morning" in text.lower() or "AM" in text:
            return "上午"
        if "下午" in text or "afternoon" in text.lower() or "PM" in text:
            return "下午"
        if "晚上" in text or "evening" in text.lower() or "night" in text.lower():
            return "晚上"
        return text.strip() or "上午"
