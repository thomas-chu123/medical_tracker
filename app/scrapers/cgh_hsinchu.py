"""
CGH (國泰綜合醫院) Scraper - 新竹院區 (area=3)

Scrapes:
1. /tw/reg/main_01.jsp?area=3  (GET)  -> department list
2. /tw/reg/main_01.jsp         (POST) -> weekly schedule page (form-based links)
3. /tw/reg/main_02.jsp         (POST) -> actual available dates per doctor/period/room
4. /tw/reg/RealTimeTable.jsp   (POST) -> real-time clinic progress

--- Schedule page structure ---
Page shows a weekly timetable with sections: 上午門診, 下午門診, 夜間門診
Each doctor slot is a JS link: javascript:sub(document.sec10111, '07931/黃漢倫', '3', '000')
  - The form name encodes: sec[PERIOD][ROOM][WEEK]
    where PERIOD 1..3 maps to 上午/下午/夜間
    ROOM is 3-digit, WEEK 1=Sun,2=Mon,3=Tue,4=Wed,5=Thu,6=Fri,7=Sat
  - The form contains hidden inputs: area, dept, room, week, sec, deptn, source, roomType
  - POSTing that form (with doctor+drn filled) to main_02.jsp yields available dates.
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

# CGH uses week=1 (Sun), 2 (Mon), ..., 7 (Sat)
# We map to Python isoweekday: Mon=1..Sun=7
WEEK_TO_ISO = {"1": 7, "2": 1, "3": 2, "4": 3, "5": 4, "6": 5, "7": 6}

SEC_TO_SESSION = {"1": "上午", "2": "下午", "3": "晚上"}


def _parse_int(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    m = re.search(r"\d+", text.strip())
    return int(m.group()) if m else None


def _roc_date_to_iso(roc: str) -> Optional[date]:
    """
    Convert ROC date string (115.03.16 or 1150316) to Python date.
    Returns None on failure.
    """
    try:
        roc = roc.strip().replace("/", ".").replace("-", ".")
        if "." in roc:
            parts = roc.split(".")
            year = int(parts[0]) + 1911
            month = int(parts[1])
            day = int(parts[2])
        else:
            # YYYMMDD or similar compact form
            year = int(roc[:3]) + 1911
            month = int(roc[3:5])
            day = int(roc[5:7])
        return date(year, month, day)
    except Exception:
        return None


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
        if resp.encoding is None or resp.encoding.upper() in ("ISO-8859-1", "LATIN-1"):
            resp.encoding = "utf-8"
        return resp.text

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _post(self, url: str, data: dict, extra_headers: dict = None, **kwargs) -> str:
        log.info(f"[{self.HOSPITAL_CODE}] POST {url} with data {data}")
        client = await self._get_client()
        merged_headers = {}
        if extra_headers:
            merged_headers.update(extra_headers)
        resp = await client.post(url, data=data, headers=merged_headers, **kwargs)
        resp.raise_for_status()
        if resp.encoding is None or resp.encoding.upper() in ("ISO-8859-1", "LATIN-1"):
            resp.encoding = "utf-8"
        return resp.text

    async def fetch_departments(self) -> list[DepartmentData]:
        url = f"{self.BASE_URL}/tw/reg/main_01.jsp?area={self.AREA}"
        html = await self._get(url)
        soup = BeautifulSoup(html, "lxml")

        departments: list[DepartmentData] = []

        # Departments are hidden forms: <form name="f1" ...><input name="dept" value="CA100">
        # Triggered by <a href="javascript:document.f1.submit();">Dept Name</a>
        forms = soup.find_all("form")
        seen_codes = set()
        sort_order = 1

        for form in forms:
            form_name = form.get("name")
            if not form_name or not form_name.startswith("f"):
                continue

            dept_input = form.find("input", {"name": "dept"})
            if not dept_input:
                continue

            code = dept_input.get("value")
            if not code or code in seen_codes:
                continue

            trigger_link = soup.find("a", href=f"javascript:document.{form_name}.submit();")
            if not trigger_link:
                continue

            name = trigger_link.get_text(strip=True)

            seen_codes.add(code)

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
        """
        Fetch available schedule slots for a department using CGH's form-based schedule.

        Flow:
        1. GET main.jsp to establish JSESSIONID cookie
        2. GET main_01.jsp?area=3 to load department list and get dept name
        3. POST main_01.jsp with area+dept+deptn to get the weekly timetable
        4. Parse javascript:sub(document.FORMNAME, 'DOCNO/DOCNAME',...) links
        5. For each unique (doctor, sec/period, room, week) combo, POST main_02.jsp to get actual dates
        """
        # Step 1: GET main.jsp first to establish JSESSIONID (critical for session auth)
        main_url = f"{self.BASE_URL}/tw/reg/main.jsp"
        await self._get(main_url)

        # Step 2: GET department list page + get dept name
        dept_list_url = f"{self.BASE_URL}/tw/reg/main_01.jsp?area={self.AREA}"
        dept_html = await self._get(dept_list_url)
        dept_name = self._extract_dept_name_from_html(dept_html, dept_code) or dept_code

        # POST to get the weekly schedule
        schedule_url = f"{self.BASE_URL}/tw/reg/main_01.jsp"
        post_data = {
            "area": self.AREA,
            "deptn": dept_name,
            "dept": dept_code,
            "source": "",
        }
        extra_headers = {
            "Referer": dept_list_url,
            "Origin": self.BASE_URL,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        html = await self._post(schedule_url, data=post_data, extra_headers=extra_headers)
        soup = BeautifulSoup(html, "lxml")

        # Step 3: Parse all javascript:sub() links
        # Pattern: javascript:sub(document.sec10111,'07931/黃漢倫','3','000');
        sub_pattern = re.compile(r"javascript:sub\(document\.(\w+),\s*'([^']+)',\s*'([^']+)',\s*'([^']+)'\)")

        # Build a dict of form_name -> form inputs
        forms_dict = {}
        for form in soup.find_all("form"):
            form_name = form.get("name", "")
            if not re.match(r"sec\d+", form_name):
                continue
            inputs = {}
            for inp in form.find_all("input"):
                n = inp.get("name")
                v = inp.get("value", "")
                if n:
                    inputs[n] = v
            forms_dict[form_name] = inputs

        # Build slot requests: key is (doc_no, sec, room, week) so we send week parameter correctly
        slot_requests: dict[tuple, dict] = {}

        for link in soup.find_all("a", href=sub_pattern):
            href = link.get("href", "")
            m = sub_pattern.search(href)
            if not m:
                continue

            form_name = m.group(1)
            emp_info = m.group(2)  # "07931/黃漢倫"
            area_val = m.group(3)
            room_type = m.group(4)
            link_text = link.get_text(strip=True)

            form_data = forms_dict.get(form_name, {})
            if not form_data:
                continue

            sec = form_data.get("sec", "1")
            room = form_data.get("room", "")
            week = form_data.get("week", "")
            deptn = form_data.get("deptn", dept_name)

            # Parse employee info
            if "/" in emp_info:
                doc_no, doc_name = emp_info.split("/", 1)
            else:
                doc_no = emp_info
                doc_name = link_text.replace("(額滿)", "").replace("(停診)", "").strip()

            if not doc_no:
                continue

            # Status
            is_full = False
            status = None
            if "停診" in link_text:
                status = "停診"
                is_full = True
            elif "額滿" in link_text:
                status = "額滿"
                is_full = True

            # Key includes week so we send week to main_02 (required by CGH server)
            key = (doc_no, sec, room, week)
            if key not in slot_requests:
                slot_requests[key] = {
                    "doc_no": doc_no,
                    "doc_name": doc_name,
                    "sec": sec,
                    "room": room,
                    "week": week,
                    "is_full": is_full,
                    "status": status,
                    "deptn": deptn,
                    "room_type": room_type,
                }

        if not slot_requests:
            log.warning(f"[{self.HOSPITAL_CODE}] No schedule form links found for {dept_code}")
            return []

        log.info(f"[{self.HOSPITAL_CODE}] Found {len(slot_requests)} doctor-period-room combos for {dept_code}")

        # Step 5: For each (doctor, sec, room, week) combo, POST to main_02.jsp to get actual dates
        slots: list[DoctorSlot] = []
        main02_url = f"{self.BASE_URL}/tw/reg/main_02.jsp"
        # Track globally seen (doc_no, sec, date) to avoid duplicates across week queries
        seen_doc_dates: set[tuple] = set()
        from datetime import timedelta

        for key, req in slot_requests.items():
            doc_no = req["doc_no"]
            doc_name = req["doc_name"]
            sec = req["sec"]
            room = req["room"]
            week = req["week"]
            deptn = req["deptn"]
            room_type = req["room_type"]
            is_full = req["is_full"]
            status = req["status"]

            post_data2 = {
                "area": self.AREA,
                "dept": dept_code,
                "room": room,
                "week": week,  # REQUIRED by CGH server to return dates
                "sec": sec,
                "doctor": doc_no,
                "deptn": deptn,
                "drn": doc_name,
                "source": "",
                "roomType": room_type,
            }
            extra_headers2 = {
                "Referer": schedule_url,
                "Origin": self.BASE_URL,
                "Content-Type": "application/x-www-form-urlencoded",
            }

            try:
                html2 = await self._post(main02_url, data=post_data2, extra_headers=extra_headers2)

                # main_02.jsp lists available dates as ROC date strings like 115.03.16
                date_strings = re.findall(r"\b(1\d{2}\.\d{1,2}\.\d{1,2})\b", html2)

                session_type = self.PERIOD_MAP.get(sec, "上午")
                for ds in date_strings:
                    d = _roc_date_to_iso(ds)
                    if not d:
                        continue
                    if d < date.today():
                        continue
                    if d > date.today() + timedelta(days=90):
                        continue
                    # Global dedup: same doctor shouldn't appear for same date+session twice
                    global_key = (doc_no, sec, str(d))
                    if global_key in seen_doc_dates:
                        continue
                    seen_doc_dates.add(global_key)

                    slots.append(DoctorSlot(
                        doctor_no=doc_no,
                        doctor_name=doc_name,
                        department_code=dept_code,
                        session_date=d,
                        session_type=session_type,
                        total_quota=None,
                        registered=None,
                        clinic_room=room,
                        is_full=is_full,
                        status=status,
                    ))

            except Exception as e:
                log.warning(f"[{self.HOSPITAL_CODE}] Error fetching dates for {doc_name}/{sec}/{room}: {e}")
                continue

        log.info(f"[{self.HOSPITAL_CODE}] Found {len(slots)} slots for dept {dept_code}")
        return slots

    def _extract_dept_name_from_html(self, html: str, dept_code: str) -> Optional[str]:
        """Extract department Chinese name from already-fetched department list HTML."""
        try:
            soup = BeautifulSoup(html, "lxml")
            for form in soup.find_all("form"):
                form_name = form.get("name", "")
                if not form_name.startswith("f"):
                    continue
                dept_input = form.find("input", {"name": "dept"})
                if not dept_input:
                    continue
                code = dept_input.get("value")
                if code == dept_code:
                    trigger_link = soup.find("a", href=f"javascript:document.{form_name}.submit();")
                    if trigger_link:
                        return trigger_link.get_text(strip=True)
        except Exception:
            pass
        return None

    async def fetch_clinic_progress(self, room: str, period: str, **kwargs) -> Optional[ClinicProgress]:
        """
        Query real-time clinic progress from RealTimeTable.jsp.
        
        國泰醫院的頁面結構複雜，可能返回：
        1. 表格行（有數據時）：診間 | 醫生 | 當前號 | 總號數...
        2. 文本行（非看診時段）：115年3月10日 上午眼科 游琇瑾醫師 非看診時段...
        
        Requires selecting area (3=Hsinchu), sec (session), and room.
        """
        url = f"{self.BASE_URL}/tw/reg/RealTimeTable.jsp"

        # The page requires: hosarea, sec, room to query progress
        data = {
            "hosarea": self.AREA,
            "sec": period,
            "room": room,
        }
        extra_headers = {
            "Referer": f"{self.BASE_URL}/tw/reg/RealTimeTable.jsp",
            "Origin": self.BASE_URL,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        try:
            html = await self._post(url, data=data, extra_headers=extra_headers)
        except Exception as e:
            log.warning(f"[{self.HOSPITAL_CODE}] Error fetching real-time progress: {e}")
            return None

        soup = BeautifulSoup(html, "lxml")
        target_doctor = kwargs.get("doctor_name", "")
        rows = soup.find_all("tr")

        log.debug(f"[{self.HOSPITAL_CODE}] fetch_clinic_progress searching for room={room}, doctor={target_doctor}, total rows={len(rows)}")

        # 遍歷所有行
        for row in rows:
            cells = row.find_all("td")
            if not cells:
                continue

            # 獲取整行文本（用於全局搜索）
            row_text = row.get_text(strip=True)

            # ───────────────────────────────────────────────────────
            # 檢查 1: 精確匹配診間代碼或醫生名字
            # ───────────────────────────────────────────────────────
            # 首先嘗試精確匹配單元格内容（第一列是診間代碼，第二列是醫生名字）
            room_found = False
            doctor_found = False
            
            if room and len(cells) > 0:
                cell_text = cells[0].get_text(strip=True)
                room_found = cell_text == room
            
            if target_doctor and len(cells) > 1:
                cell_text = cells[1].get_text(strip=True)
                # 精確匹配醫生名字（不使用 in）
                doctor_found = cell_text == target_doctor
            
            # 如果精確匹配失敗，但有多個搜索條件，不進行備選搜索
            # 這避免了誤匹配（例如搜索 "眼1" 不應該匹配 "眼10"）
            if room and target_doctor:
                # 兩個條件都要符合
                if not (room_found and doctor_found):
                    continue
            elif not (room_found or doctor_found):
                # 單個條件時，至少要符合一個
                continue

            log.debug(f"[{self.HOSPITAL_CODE}] Found potential match: room_found={room_found}, doctor_found={doctor_found}")

            # ───────────────────────────────────────────────────────
            # 檢查 2: 非看診時段、休診等狀態
            # ───────────────────────────────────────────────────────
            if "非看診時段" in row_text or "休診" in row_text:
                log.debug(f"[{self.HOSPITAL_CODE}] 非看診時段 detected")
                return ClinicProgress(
                    clinic_room=room,
                    session_type=self.PERIOD_MAP.get(period, "上午"),
                    current_number=0,
                    total_quota=None,
                    status="未開診"
                )

            # ───────────────────────────────────────────────────────
            # 檢查 3: 嘗試標準表格解析
            # ───────────────────────────────────────────────────────
            if len(cells) >= 2:
                # 試圖從表格中提取數值欄位
                numeric_values = []
                
                # 確定從哪一列開始提取數值
                # 如果有 room 匹配，表示找到了目標行，從第 2 列（index 1）開始
                # 如果只有 doctor 匹配（room 為空或未找到），從第 2 列（index 1）開始
                start_col = 1 if room_found or target_doctor else 0
                
                for i, cell in enumerate(cells):
                    # 跳過應該用於識別的列（診間代碼和醫生名字）
                    if i < 2:
                        continue
                    
                    cell_text = cell.get_text(strip=True)
                    # 跳過包含診間代碼本身或醫生名字的文本欄位
                    if room and room in cell_text:
                        continue
                    if target_doctor and target_doctor in cell_text:
                        continue
                    
                    val = _parse_int(cell_text)
                    if val is not None:
                        numeric_values.append(val)

                # 如果找到數值欄位，返回進度
                if numeric_values:
                    registered_count = None
                    waiting_count = None
                    current_number = None
                    total_quota = None

                    if len(numeric_values) >= 4:
                        # 完整結構：registered | waiting | current | total
                        registered_count = numeric_values[0]
                        waiting_count = numeric_values[1]
                        current_number = numeric_values[2]
                        total_quota = numeric_values[3]
                    elif len(numeric_values) >= 2:
                        # 簡化結構：current | total
                        current_number = numeric_values[0]
                        total_quota = numeric_values[1]
                    elif len(numeric_values) == 1:
                        current_number = numeric_values[0]

                    clinic_queue_details = []
                    if registered_count is not None:
                        clinic_queue_details.append({"registered_count": registered_count})
                    if waiting_count is not None:
                        clinic_queue_details.append({"waiting_count": waiting_count})

                    log.info(
                        f"[{self.HOSPITAL_CODE}] Clinic progress found - room={room}, doctor={target_doctor}, "
                        f"current={current_number}, total={total_quota}, registered={registered_count}"
                    )

                    return ClinicProgress(
                        clinic_room=room,
                        session_type=self.PERIOD_MAP.get(period, "上午"),
                        current_number=current_number or 0,
                        total_quota=total_quota,
                        registered_count=registered_count,
                        waiting_list=[],
                        clinic_queue_details=clinic_queue_details,
                        status="看診中" if current_number is not None else None
                    )

        log.debug(f"[{self.HOSPITAL_CODE}] No data found for room={room}, doctor={target_doctor}")
        return None

    def calculate_remaining_count(
        self,
        current_number: int,
        target_number: int,
        clinic_queue_details: list[dict],
    ) -> int:
        return max(0, target_number - current_number)
