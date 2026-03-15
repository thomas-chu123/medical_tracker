"""
TVGH_HSINCHU (臺北榮民總醫院新竹分院) 掛號系統爬蟲

Scrapes:
1. /register/listSection.jsp?type=init                     → department list (server-rendered a tags)
2. /register/listDoctor.jsp?init=init&section={dept_code}  → doctor weekly schedule (forms)
3. /tiec/OpdProgress1.jsp                                  → real-time clinic progress (pure HTTP GET with class="grid-item")

說明：
- 全部 3 個 endpoint 都是純 HTTP GET，需加 User-Agent。
- 沒有 AJAX。
"""

import asyncio
import re
from datetime import date, datetime, timedelta
from typing import Optional
from urllib.parse import urljoin

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
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://webreg.vhct.gov.tw/",
}

def _parse_int(text: Optional[str]) -> Optional[int]:
    """Extract first integer from a string."""
    if not text:
        return None
    m = re.search(r"\d+", text.strip())
    return int(m.group()) if m else None

class TvghHsinchuScraper(BaseScraper):
    HOSPITAL_CODE = "TVGH_HSINCHU"
    BASE_URL = "https://webreg.vhct.gov.tw"

    PERIOD_MAP = {"1": "上午", "2": "下午", "3": "晚上"}

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=HEADERS,
                timeout=settings.request_timeout,
                follow_redirects=True,
                verify=False, # Ignore SSL validation errors on target hospital if any 
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
        log.info(f"[{self.HOSPITAL_CODE}] GET {url} success ({len(resp.text)} chars)")
        return resp.text

    async def fetch_departments(self) -> list[DepartmentData]:
        url = f"{self.BASE_URL}/register/listSection.jsp"
        html = await self._get(url, params={"type": "init"})
        soup = BeautifulSoup(html, "lxml")

        departments: list[DepartmentData] = []
        seen_codes: set[str] = set()

        links = soup.find_all("a", href=re.compile(r"listDoctor\.jsp.*section=([A-Z0-9]+)"))
        
        current_sort_order = 1
        for link in links:
            href = link.get("href", "")
            match = re.search(r"section=([A-Z0-9]+)", href)
            if not match:
                continue
            
            code = match.group(1).strip()
            # Clean up the name string by replacing new lines or extraneous spaces 
            full_name = link.get_text(separator=' ', strip=True) 

            if not code or not full_name:
                continue

            if code in seen_codes:
                continue
            seen_codes.add(code)

            skip_keywords = ["行政", "教學", "認證", "單位", "專案", "疫苗", "自費", "巡迴", "體檢", "戒菸", "毒品"]
            if any(keyword in full_name for keyword in skip_keywords):
                log.debug(f"[{self.HOSPITAL_CODE}] Skipping non-clinical dept: {full_name}")
                continue

            departments.append(
                DepartmentData(
                    name=full_name,
                    code=code,
                    hospital_code=self.HOSPITAL_CODE,
                    category=self._categorize_department(full_name),
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
            "胸腔內科": "內科系", "胃腸肝膽": "內科系", "腎臟病科": "內科系",
            "免疫風濕": "內科系", "新陳代謝": "內科系", "感染科": "內科系",
            "家醫": "內科系", "肺炎疫苗": "內科系", "安寧緩和": "內科系", "高齡醫學": "內科系",
            "一般外科": "外科系", "神經外科": "外科系", "泌尿外科": "外科系",
            "胸腔外科": "外科系", "大腸直腸": "外科系", "重建整形": "外科系",
            "骨科部": "外科系", "婦女醫學部": "婦兒科系", "一般兒科": "婦兒科系", "健兒門診": "婦兒科系",
            "精神部": "其他專科", "皮膚科": "其他專科", "耳鼻喉頭頸外科": "其他專科",
            "眼科部": "其他專科", "復健科": "其他專科", "傳統醫學科": "其他專科", "一般牙科": "其他專科",
        }
        for k, v in name_category_map.items():
            if k in name:
                return v
        return "其他專科"

    async def fetch_schedule(self, dept_code: str) -> list[DoctorSlot]:
        url = f"{self.BASE_URL}/register/listDoctor.jsp"
        html = await self._get(url, params={"init": "init", "section": dept_code})
        soup = BeautifulSoup(html, "lxml")
        slots: list[DoctorSlot] = []

        forms = soup.find_all("form")
        for form in forms:
            name_input = form.find("input", {"name": "doctorChineseName"})
            date_input = form.find("input", {"name": "consultDateAD"})
            doc_no_input = form.find("input", {"name": "doctorNumber"})
            session_input = form.find("input", {"name": "consultNoonFlag"})

            if not all([name_input, date_input, doc_no_input, session_input]):
                continue

            doc_name_str = name_input.get("value", "").replace("醫師", "").strip()
            date_ad_str = date_input.get("value", "").strip()
            doc_no_str = doc_no_input.get("value", "").strip()
            session_flag = session_input.get("value", "").strip()
            
            # --- Fix: Extract room and registered from table cells ---
            room_str = ""
            registered = None
            parent_td = form.find_parent("td")
            if parent_td:
                parent_tr = parent_td.find_parent("tr")
                if parent_tr:
                    tds = parent_tr.find_all("td")
                    # Column 5 (index 4) is "診間"
                    if len(tds) >= 5:
                        room_str = tds[4].get_text(strip=True)
                    # Column 6 (index 5) is "已掛人數"
                    if len(tds) >= 6:
                        reg_text_td = tds[5].get_text(strip=True)
                        if reg_text_td.isdigit():
                            registered = int(reg_text_td)
            
            # Fallback to hidden input if room table parsing failed
            if not room_str:
                room_input = form.find("input", {"name": "consultRoomLocation"})
                room_str = room_input.get("value", "") if room_input else ""
            
            # Clean room string: remove "第" and "診"
            room_str = re.sub(r"[第診]", "", room_str).strip()

            if len(date_ad_str) == 8: # YYYYMMDD
                try:
                    slot_date = date(int(date_ad_str[:4]), int(date_ad_str[4:6]), int(date_ad_str[6:]))
                except ValueError:
                    continue
            else:
                continue

            session_type = "上午"
            if session_flag == "P":
                session_type = "下午"
            elif session_flag == "N":
                session_type = "晚上"

            # Extract registration info from anchor tag as fallback
            reg_link = parent_td.find("a") if parent_td else None
            reg_text = reg_link.get_text(strip=True) if reg_link else ""
            
            total_quota = None
            is_full = False
            
            if registered is None and "已掛" in reg_text:
                reg_match = re.search(r"已掛\s*(\d+)", reg_text)
                if reg_match:
                    registered = int(reg_match.group(1))
            
            if "額滿" in reg_text:
                quota_match = re.search(r"額滿\s*(\d+)", reg_text)
                if quota_match:
                    total_quota = int(quota_match.group(1))
                is_full = True
            elif "可掛" in reg_text:
                quota_match = re.search(r"可掛\s*(\d+)", reg_text)
                if quota_match:
                    total_quota = int(quota_match.group(1))

            slots.append(
                DoctorSlot(
                    doctor_no=doc_no_str,
                    doctor_name=doc_name_str,
                    department_code=dept_code,
                    session_date=slot_date,
                    session_type=session_type,
                    total_quota=total_quota,
                    registered=registered,
                    clinic_room=room_str.strip() or None,
                    is_full=is_full,
                )
            )

        log.info(f"[{self.HOSPITAL_CODE}] Found {len(slots)} doctor slots for dept_code={dept_code}")
        return slots

    async def fetch_clinic_progress(self, room: str, period: str, **kwargs) -> Optional[ClinicProgress]:
        # 'room' is actually the dept_name for this hospital, since progress is mapped by name
        url = f"{self.BASE_URL}/tiec/OpdProgress1.jsp"
        try:
            html = await self._get(url)
        except Exception as e:
            log.error(f"[{self.HOSPITAL_CODE}] Error fetching clinic progress: {e}")
            return None

        soup = BeautifulSoup(html, "lxml")
        
        # 'period' from system: '1' -> 上午診, '2' -> 下午診, '3' -> 夜間診
        period_str = self.PERIOD_MAP.get(period, period)
        if period_str == "晚上":
            period_str = "夜間診"
        elif period_str == "上午":
            period_str = "上午診"
        elif period_str == "下午":
            period_str = "下午診"

        # Find the specific panel based on period
        target_span = soup.find("span", string=re.compile(period_str))
        if not target_span:
            # We must map period to class span value 
            log.warning(f"[{self.HOSPITAL_CODE}] Could not find period span for {period_str}")
            return None

        panel_div = target_span.parent.find_next_sibling("div", class_=re.compile(r"panel.*"))
        
        if not panel_div:
            return None
        
        items = panel_div.find_all("div", class_="grid-item")
        
        # The room argument passed in will be dept_code or dept_name depending on how scheduling binds it
        # TVGH uses doctor and department names in progress
        target_dept_name = room 
        doctor_name = kwargs.get("doctor_name")
        
        found_current_number = None
        found_registered = None
        found_total_quota = None
        found_doctor = None

        for item in items:
            tds = item.find_all("td")
            if len(tds) < 2:
                continue
            
            info_text = tds[0].get_text(separator=' ', strip=True)
            number_text = tds[1].get_text(separator=' ', strip=True)
            
            # Robust matching: 
            # 1. Exact doctor match OR partial match if doctor name is in info_text
            # 2. Dept match if no doctor provided 
            match_found = False
            if doctor_name:
                # Use regex for flexible matching (ignore spaces/titles)
                clean_doc = re.escape(doctor_name)
                if re.search(clean_doc, info_text):
                    match_found = True
            elif target_dept_name and target_dept_name in info_text:
                match_found = True
                
            if match_found:
                found_current_number = _parse_int(number_text)
                
                # Check for "掛號" or "人數" in the text to extract registration count
                # Or if the number_text matches a solitary number pattern
                reg_match = re.search(r"(?:掛號|人數)\D*(\d+)", number_text)
                if reg_match:
                    found_registered = int(reg_match.group(1))
                elif number_text.isdigit():
                    # If it's just a number, it might be the current number, 
                    # but we keep the logic consistent with current_number assignment
                    pass 
                
                # Check for "總號" or "限額" if available
                quota_match = re.search(r"(?:總號|限額)\D*(\d+)", number_text)
                if quota_match:
                    found_total_quota = int(quota_match.group(1))

                doc_parts = info_text.split()
                if doc_parts:
                    found_doctor = doc_parts[0]
                break

        if found_current_number is None:
            return None

        return ClinicProgress(
            clinic_room=room,
            session_type=self.PERIOD_MAP.get(period, period),
            current_number=found_current_number,
            registered_count=found_registered,
            total_quota=found_total_quota,
            status="看診中" if found_current_number > 0 else None,
            clinic_queue_details=[{"doctor": found_doctor}] if found_doctor else []
        )

    def calculate_remaining_count(
        self,
        current_number: int,
        target_number: int,
        clinic_queue_details: list[dict],
    ) -> int:
        return max(0, target_number - current_number)
