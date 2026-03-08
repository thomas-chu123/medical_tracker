"""
CGH (國泰綜合醫院) Scraper - 新竹院區 (area=3)

Scrapes:
1. /tw/reg/main_01.jsp?area=3                -> department list
2. /tw/reg/main_01.jsp                       -> doctor weekly schedule (POST)
3. /tw/reg/RealTimeTable.jsp                 -> real-time clinic progress
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
from app.core.timezone import today_tw

settings = get_settings()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    "Referer": "https://reg.cgh.org.tw/tw/reg/main.jsp",
}

def _parse_int(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    m = re.search(r"\d+", text.strip())
    return int(m.group()) if m else None

class CGHHsinchuScraper(BaseScraper):
    HOSPITAL_CODE = "CGH_HSINCHU"
    BASE_URL = "https://reg.cgh.org.tw"
    AREA = "3"  # Hsinchu

    PERIOD_MAP = {"1": "上午", "2": "下午", "3": "晚上"}

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=HEADERS,
                timeout=settings.request_timeout,
                follow_redirects=True,
                verify=False,
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _get(self, url: str, **kwargs) -> str:
        log.info(f"[{self.HOSPITAL_CODE}] GET {url}")
        client = await self._get_client()
        resp = await client.get(url, **kwargs)
        resp.raise_for_status()
        if resp.encoding is None or resp.encoding == "ISO-8859-1":
            resp.encoding = "big5"  # CGH uses Big5
        return resp.text

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _post(self, url: str, data: dict, **kwargs) -> str:
        log.info(f"[{self.HOSPITAL_CODE}] POST {url} with data {data}")
        client = await self._get_client()
        resp = await client.post(url, data=data, **kwargs)
        resp.raise_for_status()
        if resp.encoding is None or resp.encoding == "ISO-8859-1":
            resp.encoding = "big5"
        return resp.text

    async def fetch_departments(self) -> list[DepartmentData]:
        url = f"{self.BASE_URL}/tw/reg/main_01.jsp?area={self.AREA}"
        html = await self._get(url)
        soup = BeautifulSoup(html, "lxml")

        departments: list[DepartmentData] = []
        
        # In main_01.jsp, departments are in hidden forms like:
        # <form name="f1" ...><input name="dept" value="CA100">...
        # Triggered by <a href="javascript:document.f1.submit();">Dept Name</a>
        
        forms = soup.find_all("form")
        seen_codes = set()
        sort_order = 1
        
        for form in forms:
            form_name = form.get("name")
            if not form_name or not form_name.startswith("f"):
                continue
                
            depth_input = form.find("input", {"name": "dept"})
            if not depth_input:
                continue
                
            code = depth_input.get("value")
            if not code or code in seen_codes:
                continue
                
            # Find the trigger link
            trigger_link = soup.find("a", href=f"javascript:document.{form_name}.submit();")
            if not trigger_link:
                continue
                
            name = trigger_link.get_text(strip=True)
            
            seen_codes.add(code)
            
            # Skip non-clinical depts
            skip_keywords = ["疫苗", "額滿", "代診", "COVID"]
            if any(k in name for k in skip_keywords):
                continue
                
            category = self._categorize_department(name)
            departments.append(DepartmentData(
                name=name,
                code=code,
                hospital_code=self.HOSPITAL_CODE,
                category=category,
                sort_order=sort_order
            ))
            sort_order += 1
            
        log.info(f"[{self.HOSPITAL_CODE}] Found {len(departments)} departments")
        return departments

    @staticmethod
    def _categorize_department(name: str) -> str:
        name_category_map = {
            "內科": "內科系", "兒科": "婦兒科系", "外科": "外科系",
            "婦及": "婦兒科系", "產科": "婦兒科系", "骨科": "外科系",
            "泌尿": "外科系", "眼科": "其他專科", "耳鼻喉": "其他專科",
            "皮膚": "其他專科", "精神": "其他專科", "復健": "其他專科",
            "牙科": "其他專科", "中醫": "其他專科"
        }
        for k, v in name_category_map.items():
            if k in name:
                return v
        return "其他專科"

    async def fetch_schedule(self, dept_code: str) -> list[DoctorSlot]:
        # Step 1: Visit main_01.jsp?area=3 to set state
        base_url = f"{self.BASE_URL}/tw/reg/main_01.jsp?area={self.AREA}"
        await self._get(base_url)
        
        # Step 2: POST to main_01.jsp for the specific dept
        url = f"{self.BASE_URL}/tw/reg/main_01.jsp"
        data = {
            "area": self.AREA,
            "dept": dept_code,
            "regType": "1"
        }
        headers = {
            "Referer": base_url,
            "Origin": self.BASE_URL,
            "Content-Type": "application/x-www-form-urlencoded"
        }
        html = await self._post(url, data=data, headers=headers)
        soup = BeautifulSoup(html, "lxml")
        
        slots: list[DoctorSlot] = []
        
        # Look for links with choice_date or period
        links = soup.find_all("a", href=re.compile(r"choice_date=|period="))
        
        if not links:
            log.warning(f"[{self.HOSPITAL_CODE}] No schedule links found for {dept_code}. Title: {soup.title.string if soup.title else 'No Title'}")
        
        for link in links:
            href = link.get("href", "")
            
            # Extract parameters from sub('...') or direct URL
            params_match = re.search(r"sub\('([^']+)'", href)
            if params_match:
                params_str = params_match.group(1)
            else:
                params_str = href.split("?", 1)[-1] if "?" in href else href
                
            # Parse parameters
            import urllib.parse
            params = dict(urllib.parse.parse_qsl(params_str))
            
            date_str = params.get("choice_date")
            period_code = params.get("period")
            emp_info = params.get("empNo", "")
            room = params.get("room", "")
            
            if not (date_str and period_code):
                continue
            
            try:
                session_date = datetime.strptime(date_str, "%Y%m%d").date()
            except ValueError:
                continue
                
            session_type = self.PERIOD_MAP.get(period_code, "上午")
            
            # Split empNo or get from text
            if "/" in emp_info:
                doc_no, doc_name = emp_info.split("/", 1)
            else:
                doc_no = emp_info
                doc_name = link.get_text(strip=True).replace("(額滿)", "").replace("(停診)", "").strip()
            
            if not doc_no:
                continue

            font_tag = link.find("font")
            is_full = False
            status = None
            link_text = link.get_text()
            
            if font_tag and font_tag.get("color") == "red":
                is_full = True
                status = "額滿"
            
            if "停診" in link_text:
                status = "停診"
                is_full = True
            elif "額滿" in link_text:
                status = "額滿"
                is_full = True

            slots.append(DoctorSlot(
                doctor_no=doc_no,
                doctor_name=doc_name,
                department_code=dept_code,
                session_date=session_date,
                session_type=session_type,
                total_quota=None,
                registered=None,
                clinic_room=room,
                is_full=is_full,
                status=status
            ))
            
        log.info(f"[{self.HOSPITAL_CODE}] Found {len(slots)} slots for dept {dept_code}")
        return slots

    async def fetch_clinic_progress(self, room: str, period: str, **kwargs) -> Optional[ClinicProgress]:
        url = f"{self.BASE_URL}/tw/reg/RealTimeTable.jsp"
        # The site uses 'hosarea' for area selection in progress page
        data = {"hosarea": self.AREA}
        html = await self._post(url, data=data)
        soup = BeautifulSoup(html, "lxml")
        
        target_doctor = kwargs.get("doctor_name")
        rows = soup.find_all("tr")
        
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 3:
                continue
            
            item_room = cells[0].get_text(strip=True)
            doc_name = cells[1].get_text(strip=True)
            current_num_str = cells[2].get_text(strip=True)
            total_num_str = cells[3].get_text(strip=True) if len(cells) > 3 else None
            
            # Match by room or doctor name
            is_match = False
            if target_doctor and target_doctor in doc_name:
                is_match = True
            elif room and room == item_room:
                is_match = True
                
            if is_match:
                current_number = _parse_int(current_num_str) or 0
                total_quota = _parse_int(total_num_str)
                
                return ClinicProgress(
                    clinic_room=item_room,
                    session_type=self.PERIOD_MAP.get(period, "上午"),
                    current_number=current_number,
                    total_quota=total_quota
                )
                
        return None

    def calculate_remaining_count(
        self,
        current_number: int,
        target_number: int,
        clinic_queue_details: list[dict],
    ) -> int:
        return max(0, target_number - current_number)
