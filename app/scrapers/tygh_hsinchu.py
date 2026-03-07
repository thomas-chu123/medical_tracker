"""
TYGH (東元綜合醫院) Scraper

Scrapes:
1. /WebRegDept.aspx                         -> department list
2. /WebRegList_Dept.aspx?d={dept_code}      -> doctor weekly schedule
3. /MainWebProcess.aspx                     -> real-time clinic progress
"""

import asyncio
import re
from datetime import date, datetime
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.logger import logger as log
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
}

def _parse_int(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    m = re.search(r"\d+", text.strip())
    return int(m.group()) if m else None

class TyghHsinchuScraper(BaseScraper):
    HOSPITAL_CODE = "TYGH_HSINCHU"
    BASE_URL = "https://w3.tyh.com.tw"

    PERIOD_MAP = {"1": "上午", "2": "下午", "3": "晚上"}

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=HEADERS,
                timeout=settings.request_timeout,
                follow_redirects=True,
                verify=False,  # Ignore SSL warnings for target site
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _get(self, url: str, **kwargs) -> str:
        log.info(f"[{self.HOSPITAL_CODE}] GET {url} with params {kwargs.get('params')}")
        client = await self._get_client()
        resp = await client.get(url, **kwargs)
        resp.raise_for_status()
        if resp.encoding is None:
            resp.encoding = "utf-8"
        return resp.text

    async def fetch_departments(self) -> list[DepartmentData]:
        url = f"{self.BASE_URL}/WebRegDept.aspx"
        html = await self._get(url)
        soup = BeautifulSoup(html, "lxml")

        departments: list[DepartmentData] = []
        seen_codes: set[str] = set()

        links = soup.find_all("a", href=re.compile(r"WebRegList_Dept\.aspx\?d=(\d+)"))
        current_sort_order = 1
        
        for link in links:
            href = link.get("href", "")
            match = re.search(r"d=(\d+)", href)
            if not match:
                continue
            
            code = match.group(1).strip()
            full_name = link.get_text(separator=" ", strip=True)

            if not code or not full_name:
                continue
            if code in seen_codes:
                continue
            seen_codes.add(code)

            skip_keywords = ["疫苗", "行政", "教學", "認證", "單位", "專案", "自費", "巡迴", "體檢", "戒菸", "毒品", "心理治療"]
            if any(keyword in full_name for keyword in skip_keywords):
                log.debug(f"[{self.HOSPITAL_CODE}] Skipping non-clinical dept: {full_name}")
                continue

            category = self._categorize_department(full_name)
            
            departments.append(
                DepartmentData(
                    name=full_name,
                    code=code,
                    hospital_code=self.HOSPITAL_CODE,
                    category=category,
                    sort_order=current_sort_order
                )
            )
            current_sort_order += 1

        log.info(f"[{self.HOSPITAL_CODE}] Found {len(departments)} departments after dedup")
        return departments

    @staticmethod
    def _categorize_department(name: str) -> str:
        name_category_map = {
            "一般內科": "內科系", "神經內科": "內科系", "心臟內科": "內科系",
            "胸腔內科": "內科系", "腸胃肝膽內科": "內科系", "腎臟內科": "內科系",
            "免疫風濕科": "內科系", "新陳代謝科": "內科系", "感染科": "內科系",
            "家庭醫學科": "內科系", 
            "一般外科": "外科系", "神經外科": "外科系", "泌尿科": "外科系",
            "胸腔外科": "外科系", "大腸直腸外科": "外科系", "整形外科": "外科系",
            "骨科": "外科系", "心臟血管外科": "外科系", "減重門診": "外科系",
            "婦產科": "婦兒科系", "小兒科": "婦兒科系", "小兒外科": "婦兒科系",
            "精神科": "其他專科", "皮膚科": "其他專科", "耳鼻喉科": "其他專科",
            "眼科": "其他專科", "復健科": "其他專科", "中醫科": "其他專科", "一般牙科": "其他專科",
            "牙科部": "其他專科"
        }
        for k, v in name_category_map.items():
            if k in name:
                return v
        return "其他專科"

    async def fetch_schedule(self, dept_code: str) -> list[DoctorSlot]:
        url = f"{self.BASE_URL}/WebRegList_Dept.aspx"
        html = await self._get(url, params={"d": dept_code})
        soup = BeautifulSoup(html, "lxml")
        slots: list[DoctorSlot] = []

        # Find doctor links
        # Doctor anchors are like <a href="WebRegList_Doct.aspx?dn=0709&d=07">鄧堯州</a>
        links = soup.find_all("a", href=re.compile(r"WebRegList_Doct\.aspx\?dn=([A-Za-z0-9_]+)&d="))
        
        seen = set()
        doctors = []
        for a in links:
            href = a["href"]
            match = re.search(r"dn=([A-Za-z0-9_]+)", href)
            if match:
                doc_no = match.group(1).strip()
                doc_name = a.get_text(strip=True).replace("醫師", "").strip()
                if doc_no not in seen:
                    seen.add(doc_no)
                    doctors.append((doc_no, doc_name))

        # We will need to visit each doctor's page to get their schedule blocks
        import asyncio
        sem = asyncio.Semaphore(5)

        async def fetch_doctor(doc_no, doc_name):
            async with sem:
                return await self._fetch_single_doctor_schedule(dept_code, doc_no, doc_name)

        results = await asyncio.gather(*[fetch_doctor(no, name) for no, name in doctors], return_exceptions=True)
        for r in results:
            if isinstance(r, list):
                slots.extend(r)

        log.info(f"[{self.HOSPITAL_CODE}] Found {len(slots)} slots for dept={dept_code}")
        return slots

    async def _fetch_single_doctor_schedule(self, dept_code: str, doc_no: str, doc_name: str) -> list[DoctorSlot]:
        url = f"{self.BASE_URL}/WebRegList_Doct.aspx"
        html = await self._get(url, params={"dn": doc_no, "d": dept_code})
        soup = BeautifulSoup(html, "lxml")
        
        slots = []
        inputs = soup.find_all("input", {"name": "RadioDoct"})
        
        for inp in inputs:
            val = inp.get("value")
            # val typically looks like: 0A1150309A1A07A1
            parts = val.split("A")
            if len(parts) < 4:
                continue
                
            date_str = parts[1]
            session_id = parts[2]
            
            try:
                year = int(date_str[:3]) + 1911
                month = int(date_str[3:5])
                day = int(date_str[5:7])
                slot_date = date(year, month, day)
            except ValueError:
                continue
                
            label = inp.find_next("label")
            label_text = label.get_text(separator='|', strip=True) if label else ""
            
            is_full = "額滿" in label_text or "滿號" in label_text or "停診" in label_text or "時段已過" in label_text
            status = "休診" if "停診" in label_text else ("額滿" if "額滿" in label_text or "滿號" in label_text else None)
            
            reg_match = re.search(r"已掛號:?(\d+)人?", label_text)
            registered = int(reg_match.group(1)) if reg_match else None
            
            session_type = self._normalize_session_type(session_id)
            
            slots.append(DoctorSlot(
                doctor_no=doc_no,
                doctor_name=doc_name,
                department_code=dept_code,
                session_date=slot_date,
                session_type=session_type,
                total_quota=None,
                registered=registered,
                clinic_room=None,
                is_full=is_full,
                status=status
            ))

        return slots

    @staticmethod
    def _normalize_session_type(text: str) -> str:
        if "上" in text:
            return "上午"
        if "下" in text:
            return "下午"
        if "夜" in text or "晚" in text:
            return "晚上"
        return "上午"

    async def fetch_clinic_progress(self, room: str, period: str, **kwargs) -> Optional[ClinicProgress]:
        # 'room' maps to department code usually, but looking at 'MainWebProcess.aspx' 
        # it lists all departments on a single page in tables.
        
        url = f"{self.BASE_URL}/MainWebProcess.aspx"
        try:
            html = await self._get(url)
        except Exception as e:
            log.error(f"[{self.HOSPITAL_CODE}] Error fetching clinic progress: {e}")
            return None

        soup = BeautifulSoup(html, "lxml")
        
        page_text = soup.get_text()
        if "目前非轉檔時段" in page_text:
            return ClinicProgress(
                clinic_room=room,
                session_type=self.PERIOD_MAP.get(period, period),
                current_number=0,
                status="未開診",
                registered_count=0
            )

        # Map period 1,2,3 to timeslot
        period_str = self.PERIOD_MAP.get(period, period)
        
        # We find the table that has 'room' text as Header or within td
        # TYGH uses li elements for modern layout
        target_number = None
        target_doctor = None
        target_room = None
        status = None

        items = soup.find_all("li", class_="number-light-box")
        for item in items:
            room_tag = item.find("h2", class_="room")
            name_tag = item.find("p", class_="name")
            number_tag = item.find("span", class_="number")
            
            if not room_tag or not name_tag or not number_tag:
                continue
                
            item_room = room_tag.get_text(strip=True)
            doc_name = name_tag.get_text(strip=True)
            number_str = number_tag.get_text(strip=True)
            
            kwargs_doctor = kwargs.get('doctor_name', '')
            
            is_match = False
            if kwargs_doctor and kwargs_doctor in doc_name:
                is_match = True
            elif str(room) == item_room:
                is_match = True
                
            if is_match:
                target_number = _parse_int(number_str)
                target_doctor = doc_name
                target_room = item_room
                break

        if target_number is None and not items:
            tables = soup.find_all("table")
            for table in tables:
                rows = table.find_all("tr")
                if len(rows) > 0:
                    for row in rows:
                        cells = row.find_all(["td", "th"])
                        if len(cells) >= 3:
                            dept_name = cells[0].get_text(strip=True)
                            doc_name = cells[1].get_text(strip=True)
                            number_str = cells[2].get_text(strip=True)
                            
                            kwargs_dept = kwargs.get('dept_name', '')
                            kwargs_doctor = kwargs.get('doctor_name', '')
                            
                            if (kwargs_doctor and kwargs_doctor in doc_name) or (kwargs_dept and kwargs_dept in dept_name):
                                target_number = _parse_int(number_str)
                                target_doctor = doc_name
                                target_room = dept_name # the page uses dept_name position for rooms in this older format
                                break
                if target_number is not None:
                    break

        if target_number is None and not status:
            return None

        # Return matching format
        return ClinicProgress(
            clinic_room=target_room or room,
            session_type=period_str,
            current_number=target_number or 0,
            status=status,
            clinic_queue_details=[{"doctor": target_doctor}] if target_doctor else []
        )

    def calculate_remaining_count(
        self,
        current_number: int,
        target_number: int,
        clinic_queue_details: list[dict],
    ) -> int:
        return max(0, target_number - current_number)

