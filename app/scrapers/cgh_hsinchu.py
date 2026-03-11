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

    ✅ 問題3修正：增強的日期轉換邏輯
    支持格式：
    - "115.03.16" / "115-03-16" → ISO 2026-03-16
    - "1150316" → ISO 2026-03-16

    驗證項目：
    - 月份範圍：1-12
    - 日期範圍：1-31
    - 年份有效性：確保轉換後是合理的西元年份
    """
    try:
        roc = roc.strip()
        if not roc:
            return None

        # ✅ 問題3修正：標準化分隔符
        roc_normalized = roc.replace("/", ".").replace("-", ".")

        # ✅ 問題3修正：分情況處理
        if "." in roc_normalized:
            # 格式：115.03.16 或 115.3.16
            parts = roc_normalized.split(".")
            if len(parts) != 3:
                log.warning(f"[{__name__}] Invalid ROC date format (wrong part count): {roc}")
                return None
            roc_year = int(parts[0])
            month = int(parts[1])
            day = int(parts[2])
        else:
            # 格式：1150316 或 115316（7 位數或 6 位數）
            if len(roc) not in (7, 6):
                log.warning(f"[{__name__}] Invalid ROC date format (wrong length): {roc}")
                return None

            roc_year = int(roc[:3])
            # ✅ 問題3修正：支持 6 位數格式 (115316 表示 115年3月16日，需要補零)
            if len(roc) == 6:
                month = int(roc[3])
                day = int(roc[4:6])
            else:
                month = int(roc[3:5])
                day = int(roc[5:7])

        # ✅ 問題3修正：驗證月份和日期的有效性
        if not (1 <= month <= 12):
            log.warning(f"[{__name__}] Invalid month: {month} from {roc}")
            return None

        if not (1 <= day <= 31):
            log.warning(f"[{__name__}] Invalid day: {day} from {roc}")
            return None

        # ✅ 問題3修正：ROC 轉西元（民國年份 + 1911）
        gregorian_year = roc_year + 1911

        # ✅ 問題3修正：驗證轉換後的年份合理性（確保不是負數或異常大的值）
        if gregorian_year < 1900 or gregorian_year > 2100:
            log.warning(f"[{__name__}] Gregorian year out of reasonable range: {gregorian_year} from ROC {roc_year}")
            return None

        # ✅ 問題3修正：嘗試創建日期物件，會自動驗證日期有效性
        return date(gregorian_year, month, day)

    except (ValueError, IndexError) as e:
        log.error(f"[{__name__}] Date conversion failed for '{roc}': {e}")
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
        
        ✅ 修正版本：正確解析國泰表格結構
        國泰的表格結構為：
        - 目前看診序號：14
        - 尚未就診號人數：1, 3, 6, 8, 10, 12, 14, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28

        表格通常包含以下行：
        1. 標籤行：包含"目前看診序號"和"尚未就診號人數"
        2. 數據行：診間 | 醫生 | [當前號] | [等候號碼列表...]
        3. 非看診時段提示
        """
        url = f"{self.BASE_URL}/tw/reg/RealTimeTable.jsp"

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

        # 遍歷所有行尋找數據行
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 2:
                continue

            row_text = row.get_text(strip=True)

            # ✅ 檢查各種診間狀態
            if "非看診時段" in row_text or "休診" in row_text:
                log.debug(f"[{self.HOSPITAL_CODE}] 非看診時段 detected")
                return ClinicProgress(
                    clinic_room=room,
                    session_type=self.PERIOD_MAP.get(period, "上午"),
                    current_number=0,
                    total_quota=None,
                    status="未開診"
                )

            # ✅ 檢查已結束看診
            if "已結束看診" in row_text:
                log.debug(f"[{self.HOSPITAL_CODE}] 已結束看診 detected")
                return ClinicProgress(
                    clinic_room=room,
                    session_type=self.PERIOD_MAP.get(period, "上午"),
                    current_number=0,
                    total_quota=None,
                    status="已結束"
                )

            # ✅ 嘗試匹配診間和醫生
            cell_texts = [cell.get_text(strip=True) for cell in cells]

            room_found = False
            doctor_found = False

            if room and len(cell_texts) > 0:
                room_cell = cell_texts[0].replace("號", "").replace(" ", "")
                room_param = room.replace("號", "").replace(" ", "")
                room_found = room_cell == room_param

            if target_doctor and len(cell_texts) > 1:
                doctor_found = cell_texts[1] == target_doctor

            # 匹配邏輯
            if room and target_doctor:
                if not (room_found and doctor_found):
                    continue
            elif room and not room_found:
                continue
            elif target_doctor and not doctor_found:
                continue

            log.debug(f"[{self.HOSPITAL_CODE}] Found potential match: room_found={room_found}, doctor_found={doctor_found}")

            # ✅ 提取當前號碼和等候號碼
            # 從匹配的行開始，第3列及以後都是號碼
            current_number = None
            all_queue_numbers = []

            if len(cells) >= 3:
                for i in range(2, len(cells)):
                    cell_text = cell_texts[i] if i < len(cell_texts) else ""

                    # 跳過特殊文本
                    if cell_text in ("無", "無看診", "N/A", "-", ""):
                        continue
                    
                    # 提取號碼
                    numbers = re.findall(r"\d+", cell_text)
                    for num_str in numbers:
                        try:
                            num = int(num_str)
                            all_queue_numbers.append(num)
                        except ValueError:
                            continue

                # ✅ 解析號碼邏輯
                if all_queue_numbers:
                    # 排序並去重
                    all_queue_numbers = sorted(set(all_queue_numbers))
                    log.debug(f"[{self.HOSPITAL_CODE}] Extracted queue numbers: {all_queue_numbers}")

                    # 第一個號碼通常是當前看診號
                    current_number = all_queue_numbers[0]

                    # 計算等候人數：最後一個號碼減去當前號
                    waiting_count = all_queue_numbers[-1] - current_number if len(all_queue_numbers) > 1 else 0

                    log.info(
                        f"[{self.HOSPITAL_CODE}] Clinic progress - room={room}, doctor={target_doctor}, "
                        f"current={current_number}, waiting={waiting_count}, queue={all_queue_numbers[:5]}..."
                    )

                    return ClinicProgress(
                        clinic_room=room,
                        session_type=self.PERIOD_MAP.get(period, "上午"),
                        current_number=current_number,
                        total_quota=all_queue_numbers[-1] if all_queue_numbers else None,
                        registered_count=len(all_queue_numbers),
                        waiting_list=[],
                        clinic_queue_details=[{"queue_numbers": all_queue_numbers}],
                        status="看診中"
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
