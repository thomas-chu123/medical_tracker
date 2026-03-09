"""
HMMH (馬偕紀念醫院新竹分院) Scraper

Scrapes:
1. /progress.php                                      → department list (from select[name=dept] — fully server-rendered)
2. /register_divide.php?depid={code}                  → doctor weekly schedule (fully server-rendered, drcode in onclick attrs)
3. /register_single_doctor.php?depid={}&drcode={}     → individual doctor appointment slots (fully server-rendered)
4. /progressstatus.php?dept={dept}&ap={period}        → real-time clinic progress (plain HTTP GET)

說明：
- 全部 4 個 endpoint 都是純 HTTP GET，不需要 Selenium 。
- register_divide.php 表格中的每個儲格都已包含 onclick="registergo('{internal_depid}','{drcode}')"，
  還有「醫師名<br>drcode」格式，不需要 AJAX。
- deptimetable.php AJAX endpoint 在直接呼叫時會回傳 500 （server-side 內部傳遞方式），不需使用。
- find_division.php 的科別下拉選單是 AJAX 動態產生，但已可從 progress.php 取得完整名單。
"""

import asyncio
import re
import random
from datetime import date, datetime, timedelta
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.logger import logger as log
from app.scrapers.base import BaseScraper, DepartmentData, DoctorSlot, ClinicProgress
from app.config import get_settings

settings = get_settings()

RANDOM_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Safari/605.1.15",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_3_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Mobile/15E148 Safari/604.1",
]

DEFAULT_HEADERS = {
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.hc.mmh.org.tw/",
}


def _parse_int(text: Optional[str]) -> Optional[int]:
    """Extract first integer from a string."""
    if not text:
        return None
    m = re.search(r"\d+", text.strip())
    return int(m.group()) if m else None


class HMMHScraper(BaseScraper):
    HOSPITAL_CODE = "HMMH"
    BASE_URL = "https://www.hc.mmh.org.tw"
    
    # Regular expression patterns
    DEPT_CODE_PATTERN = re.compile(r"depid=(\d+)")
    DOC_CODE_PATTERN = re.compile(r"drcode=([A-Za-z0-9]+)")
    DATE_PATTERN = re.compile(r"(\d{4})[/-](\d{2})[/-](\d{2})")  # AD year format

    # Period mapping: 1=上午, 2=下午, 3=晚上
    PERIOD_MAP = {"1": "上午", "2": "下午", "3": "晚上"}
    PERIOD_REVERSE_MAP = {"上午": "1", "下午": "2", "晚上": "3"}

    def __init__(self):
        super().__init__()
        self._client: Optional[httpx.AsyncClient] = None
        self._internal_dept_cache: dict[str, str] = {}
        self._cache_lock = asyncio.Lock()

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=self._get_headers(),
                timeout=settings.request_timeout,
                follow_redirects=True,
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def _get_headers(self) -> dict:
        headers = DEFAULT_HEADERS.copy()
        headers["User-Agent"] = random.choice(RANDOM_USER_AGENTS)
        return headers

    async def _apply_random_delay(self):
        """Add a random delay between 2 to 5 seconds to avoid IP blocking."""
        delay = random.uniform(2.0, 5.0)
        log.debug(f"[HMMH] Applying random delay: {delay:.2f}s")
        await asyncio.sleep(delay)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _get(self, url: str, **kwargs) -> str:
        await self._apply_random_delay()
        log.info(f"[HMMH] GET {url} with params {kwargs.get('params')}")
        client = await self._get_client()
        # Ensure each request potentially has a different User-Agent
        kwargs.setdefault("headers", self._get_headers())
        resp = await client.get(url, **kwargs)
        resp.raise_for_status()
        log.info(f"[HMMH] GET {url} success ({len(resp.text)} chars)")
        return resp.text

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _post(self, url: str, data: dict) -> str:
        await self._apply_random_delay()
        log.info(f"[HMMH] POST {url} with data {data}")
        client = await self._get_client()
        headers = self._get_headers()
        resp = await client.post(url, data=data, headers=headers)
        resp.raise_for_status()
        return resp.text

    # ─────────────────────────────────────────────────────────
    # 1. Fetch department list
    # ─────────────────────────────────────────────────────────
    async def _fetch_registration_id_map(self) -> dict[str, str]:
        """
        Scrape find_division.php to build a mapping of department name -> Registration ID (depid).
        Registration IDs are used for fetching doctor schedules (register_divide.php).
        """
        url = f"{self.BASE_URL}/find_division.php"
        try:
            html = await self._get(url)
            soup = BeautifulSoup(html, "lxml")
            
            mapping = {}
            # Links like <a href='register_divide.php?depid=217'>神經內科</a>
            # Also handle absolute URLs just in case
            links = soup.find_all("a", href=re.compile(r"register_divide\.php\?depid="))
            
            for link in links:
                href = link.get("href", "")
                name = link.get_text(strip=True)
                
                match = re.search(r"depid=([^&]+)", href)
                if match and name:
                    code = match.group(1)
                    # Use the last part of the name if it contains "-" or "部"
                    # Hospital sometimes uses "內科部-神經內科" but we just want "神經內科"
                    clean_name = name.split("-")[-1].split("部")[-1]
                    mapping[clean_name] = code
                    # Also store full name just in case mapping is exact
                    mapping[name] = code
                    
            log.info(f"[HMMH] Built dynamic registration ID map with {len(mapping)} entries")
            return mapping
        except Exception as e:
            log.error(f"[HMMH] Error building registration ID map: {e}")
            return {}

    async def fetch_departments(self) -> list[DepartmentData]:
        """
        Scrape department list from progress.php and map them to registration IDs from find_division.php.

        progress.php provides the list of active clinical departments and their "Progress IDs" (value of select[name=dept]).
        find_division.php provides the "Registration IDs" used for schedules.
        """
        # First get the registration ID map
        reg_map = await self._fetch_registration_id_map()

        url = f"{self.BASE_URL}/progress.php"
        html = await self._get(url)
        soup = BeautifulSoup(html, "lxml")

        departments: list[DepartmentData] = []
        seen_codes: set[str] = set()

        select = soup.find("select", {"name": "dept"})
        if not select:
            log.warning("[HMMH] Could not find select[name=dept] in progress.php")
            return departments

        options = select.find_all("option")
        log.info(f"[HMMH] Found {len(options)} options in dept select")

        current_sort_order = 1
        for option in options:
            code = option.get("value", "").strip()
            full_name = option.get_text(strip=True)  # e.g. "內科部-胃腸肝膽科"

            # Skip placeholder option (empty value)
            if not code or not full_name or full_name == "請選擇":
                continue

            # Deduplicate: some codes appear multiple times (different special clinics share a dept code)
            if code in seen_codes:
                log.debug(f"[HMMH] Skipping duplicate dept code='{code}' for '{full_name}'")
                continue
            seen_codes.add(code)

            # Split "部門-科別" to extract just the department name
            if "-" in full_name:
                category_prefix, dept_name = full_name.split("-", 1)
            else:
                category_prefix = ""
                dept_name = full_name

            # Dynamic Mapping to Registration ID
            # If we found an ID for this department in find_division.php, use it as the primary code.
            # This ensures fetch_schedule uses the correct Registration ID (e.g. 217 for Neurology).
            reg_code = reg_map.get(dept_name) or reg_map.get(full_name)
            if reg_code:
                if reg_code != code:
                    log.info(f"[HMMH] Mapping department '{dept_name}': Progress ID {code} -> Registration ID {reg_code}")
                code = reg_code

            # Skip administrative/non-clinical departments
            skip_keywords = ["行政", "教學", "認證", "單位", "專案", "疫苗", "自費", "特別門診"]
            if any(keyword in full_name for keyword in skip_keywords):
                log.debug(f"[HMMH] Skipping non-clinical dept: {full_name}")
                continue

            departments.append(
                DepartmentData(
                    name=dept_name,
                    code=code,
                    hospital_code=self.HOSPITAL_CODE,
                    category=self._categorize_department(dept_name, category_prefix),
                    sort_order=current_sort_order
                )
            )
            log.debug(f"[HMMH] Added dept: code={code}, name={dept_name}")
            current_sort_order += 1

        log.info(f"[HMMH] Found {len(departments)} departments after dedup")
        return departments

    @staticmethod
    def _categorize_department(name: str, category_prefix: str = "") -> str:
        """Categorize department based on name and the prefix from the select option."""
        # Use the prefix from the select option (e.g. "內科部" → "內科系")
        prefix_map = {
            "內科部": "內科系",
            "外科部": "外科系",
            "婦兒部": "婦兒科系",
            "婦產部": "婦兒科系",
            "小兒部": "婦兒科系",
        }
        if category_prefix in prefix_map:
            return prefix_map[category_prefix]

        # Fallback to name-based matching
        name_category_map = {
            # 內科系
            "一般內科": "內科系", "神經內科": "內科系", "心臟內科": "內科系",
            "心臟血管內科": "內科系", "胸腔內科": "內科系", "腸胃肝膽內科": "內科系",
            "胃腸肝膽科": "內科系", "消化內科": "內科系", "腎臟內科": "內科系",
            "風濕免疫科": "內科系", "過敏免疫風濕科": "內科系", "新陳代謝科": "內科系",
            "內分泌暨新陳代謝科": "內科系", "內分泌新陳代謝科": "內科系",
            "感染科": "內科系", "家庭醫學科": "內科系", "精神科": "內科系",
            "血液腫瘤科": "內科系", "老年醫學科": "內科系",

            # 外科系
            "一般外科": "外科系", "神經外科": "外科系", "心臟血管外科": "外科系",
            "胸腔外科": "外科系", "大腸直腸外科": "外科系", "整形外科": "外科系",
            "美容門診": "外科系", "泌尿科": "外科系", "骨科": "外科系",
            "乳房外科": "外科系", "減重暨代謝手術門診": "外科系", "外傷科": "外科系",
            "小兒外科": "外科系",

            # 婦兒科系
            "婦產科": "婦兒科系", "兒科": "婦兒科系", "兒童科": "婦兒科系",

            # 其他專科
            "眼科": "其他專科", "耳鼻喉科": "其他專科", "耳鼻喉頭頸外科": "其他專科",
            "牙科": "其他專科", "復健科": "其他專科", "皮膚科": "其他專科",
            "中醫科": "其他專科", "放射腫瘤科": "其他專科", "疼痛科": "其他專科",
            "職業病科": "其他專科",
        }

        return name_category_map.get(name, "其他專科")

    # ─────────────────────────────────────────────────────────
    # 2. Fetch doctor slots for a department (weekly timetable)
    # ─────────────────────────────────────────────────────────
    async def fetch_schedule(self, dept_code: str) -> list[DoctorSlot]:
        """
        Scrape doctor weekly schedule from register_divide.php (pure HTTP, no Selenium).

        頁面結構：<table id="tblSch">
        - 表頭列：診間 | 星期一(上/下/夠) | 星期二 ... | 星期六
        - 資料列：每個 td 內包含 onclick="registergo('{internal_depid}','{drcode}')"
          和「醫師名<br>drcode」文字（已包含在原始 HTML 中，非 AJAX）。

        drcode 可互接 register_single_doctor.php 得到詳細採診資訊。
        """
        log.info(f"[HMMH] fetch_schedule for dept_code={dept_code}")

        url = f"{self.BASE_URL}/register_divide.php"
        html = await self._get(url, params={"depid": dept_code})
        soup = BeautifulSoup(html, "lxml")

        # Determine current week start (Monday)
        today = date.today()
        days_since_monday = today.weekday()  # 0=Mon, 6=Sun
        week_start = today - timedelta(days=days_since_monday)  # This Monday

        slots: list[DoctorSlot] = []

        # Find the weekly schedule table
        table = soup.find("table", id="tblSch")
        if not table:
            log.warning(f"[HMMH] No #tblSch table found for depid={dept_code}")
            return slots

        rows = table.find_all("tr")
        log.debug(f"[HMMH] Found {len(rows)} rows in #tblSch")

        # Row 0: weekday headers (星期一 .. 星期六), each colspan=3 (上/下/晚)
        # Row 1: session type headers (上午/下午/晚上 repeated 6 times)
        # Row 2+: clinic room + 18 cells (6 days x 3 sessions)
        SESSION_TYPES = ["上午", "下午", "晚上"]  # indices 0,1,2 within each day block
        DAY_COUNT = 6  # Mon-Sat

        for row in rows[2:]:  # Skip header rows
            cells = row.find_all(["td", "th"])
            if not cells:
                continue

            # First cell is the clinic room number (e.g. "13", "14")
            clinic_room = cells[0].get_text(strip=True)
            data_cells = cells[1:]  # 18 cells: day0_am, day0_pm, day0_eve, day1_am ...

            for cell_idx, cell in enumerate(data_cells):
                if cell_idx >= DAY_COUNT * 3:
                    break  # Only process Mon-Sat

                day_offset = cell_idx // 3    # 0=Mon, 1=Tue, ... 5=Sat
                session_idx = cell_idx % 3    # 0=上午, 1=下午, 2=夠診

                # Extract drcode from onclick="registergo('{internal_depid}','{drcode}')"
                onclick = cell.get("onclick", "") or ""
                # Also check anchor tags inside
                anchor = cell.find("a")
                if anchor:
                    onclick = anchor.get("onclick", "") or onclick

                # Extract internal_depid AND drcode from onclick
                # Pattern: registergo('{internal_depid}','{drcode}') e.g. registergo('68','4301')
                onclick_match = re.search(r"registergo\('([^']+)','([^']+)'\)", onclick)
                if not onclick_match:
                    # No doctor in this slot
                    continue
                internal_depid = onclick_match.group(1)  # e.g. '68' (needed for register_single_doctor.php)
                drcode = onclick_match.group(2)           # e.g. '4301'

                # Extract doctor name and any special note from cell text
                cell_text = cell.get_text(separator="\n", strip=True)
                doctor_info = self._parse_doctor_info(cell_text)
                if not doctor_info:
                    # Try to get name from anchor text if present
                    if anchor:
                        doctor_info = self._parse_doctor_info(anchor.get_text(separator="\n", strip=True))

                doctor_name = doctor_info.get("name") if doctor_info else None
                special_note = doctor_info.get("note") if doctor_info else None

                slot_date = week_start + timedelta(days=day_offset)
                session_type = SESSION_TYPES[session_idx]

                slot = DoctorSlot(
                    doctor_no=drcode,
                    doctor_name=doctor_name or f"drcode:{drcode}",
                    department_code=dept_code,
                    session_date=slot_date,
                    session_type=session_type,
                    total_quota=None,
                    registered=None,
                    clinic_room=clinic_room,
                    is_full=False,
                    internal_dept_code=internal_depid,  # For use with register_single_doctor.php
                )
                slots.append(slot)
                log.debug(
                    f"[HMMH] Added slot: {doctor_name}({drcode}) "
                    f"{slot_date.strftime('%Y-%m-%d')}({['Mon','Tue','Wed','Thu','Fri','Sat'][day_offset]}) "
                    f"{session_type} room={clinic_room}"
                )

        log.info(f"[HMMH] Found {len(slots)} doctor slots for dept_code={dept_code}")
        return slots

    # ─────────────────────────────────────────────────────────
    # 2b. Fetch individual doctor appointment availability
    # ─────────────────────────────────────────────────────────
    async def fetch_single_doctor_schedule(
        self, dept_code: str, dr_code: str, doctor_name: str = ""
    ) -> list[DoctorSlot]:
        """
        Fetch appointment availability for a single doctor.

        Endpoint (fully server-rendered, no AJAX):
          /register_single_doctor.php?depid={dept_code}&drcode={dr_code}

        表格格式：
          日期 | 上午 | 下午 | 晚間
        每格內容：空=無採診 | 「初診(可掛)」/「複診(可掛)」 | 「滿號」

        Args:
            dept_code: The department code (depid parameter)
            dr_code:   The doctor code (drcode parameter)
            doctor_name: Doctor name (optional; pass from fetch_schedule to avoid
                         having to parse from the page heading which is unreliable)

        Returns DoctorSlot list with is_full info.
        """
        log.info(f"[HMMH] fetch_single_doctor_schedule: depid={dept_code}, drcode={dr_code}")

        url = f"{self.BASE_URL}/register_single_doctor.php"
        html = await self._get(url, params={"depid": dept_code, "drcode": dr_code})
        soup = BeautifulSoup(html, "lxml")

        slots: list[DoctorSlot] = []

        table = soup.find("table", id="tblSch")
        if not table:
            log.warning(f"[HMMH] No #tblSch in register_single_doctor depid={dept_code} drcode={dr_code}")
            return slots

        # Use provided name or fall back to dr_code as identifier
        if not doctor_name:
            doctor_name = f"drcode:{dr_code}"
        tbody = table.find("tbody")
        rows = tbody.find_all("tr") if tbody else table.find_all("tr")[1:]

        SESSION_MAP = {"上午": 0, "下午": 1, "晚上": 2}
        SESSIONS = ["上午", "下午", "晚上"]

        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 2:
                continue

            date_text = cells[0].get_text(strip=True)  # e.g. "2026/03/06(五)"
            date_match = re.search(r"(\d{4})/(\d{2})/(\d{2})", date_text)
            if not date_match:
                continue

            slot_date = date(
                int(date_match.group(1)),
                int(date_match.group(2)),
                int(date_match.group(3)),
            )

            # cells[1]=上午, cells[2]=下午, cells[3]=晚間
            for i, session_name in enumerate(SESSIONS):
                if i + 1 >= len(cells):
                    break
                cell = cells[i + 1]
                cell_text = cell.get_text(separator=" ", strip=True)

                # Determine availability
                if not cell_text or cell_text.isspace():
                    continue  # No clinic this session

                is_full = "滿號" in cell_text
                can_book_first = "初診(可掛)" in cell_text
                can_book_return = "複診(可掛)" in cell_text

                # Skip if positively indicates no clinic (only whitespace/small marker)
                if not (is_full or can_book_first or can_book_return or len(cell_text) > 2):
                    continue

                slot = DoctorSlot(
                    doctor_no=dr_code,
                    doctor_name=doctor_name,
                    department_code=dept_code,
                    session_date=slot_date,
                    session_type=session_name,
                    total_quota=None,
                    registered=None,
                    clinic_room=None,
                    is_full=is_full,
                )
                slots.append(slot)
                log.debug(
                    f"[HMMH] Slot: {slot_date} {session_name} "
                    f"full={is_full} first={can_book_first} return={can_book_return}"
                )

        log.info(f"[HMMH] fetch_single_doctor_schedule: {len(slots)} slots for drcode={dr_code}")
        return slots

    @staticmethod
    def _parse_doctor_info(text: str) -> Optional[dict]:
        """
        解析診間單元格中的醫生信息
        
        格式: "醫生名 醫生代碼 特殊說明"
        例如: 
          - "江瑞凡 4948 靜脈曲張特診含美容雷射"
          - "吳宥達 4873 含甲狀腺腫瘤診(9:30開始)"
          - "陳子堯 2114 含外傷科門診"
        
        Returns:
            {"name": "江瑞凡", "code": "4948"} 或 None
        """
        text = text.strip()
        if not text or len(text) < 3:
            return None
        
        # 分割文本
        parts = text.split()
        if len(parts) < 2:
            return None
        
        doctor_name = parts[0]
        
        # 檢查醫生名是否為有效的中文名字（通常 2-4 字）
        if not (2 <= len(doctor_name) <= 4):
            return None
        
        # 検查是否包含中文字符（簡易檢查）
        if not any('\u4e00' <= c <= '\u9fff' for c in doctor_name):
            return None
        
        # 尋找醫生代碼 (4 位數字或混合)
        doctor_code = None
        for part in parts[1:]:
            # 嘗試提取純數字代碼
            if part.isdigit() and len(part) >= 3:
                doctor_code = part
                break
            # 或提取開頭的數字
            match = re.match(r'^(\d{3,})', part)
            if match:
                doctor_code = match.group(1)
                break
        
        if not doctor_code:
            return None
        
        return {
            "name": doctor_name,
            "code": doctor_code
        }

    async def _get_internal_dept_code(self, dept_code: str, doctor_name: str) -> Optional[str]:
        cache_key = f"{dept_code}_{doctor_name}"
        async with self._cache_lock:
            if cache_key in self._internal_dept_cache:
                return self._internal_dept_cache[cache_key]
            
        slots = await self.fetch_schedule(dept_code)
        
        async with self._cache_lock:
            for slot in slots:
                if slot.doctor_name and slot.internal_dept_code:
                    self._internal_dept_cache[f"{dept_code}_{slot.doctor_name}"] = slot.internal_dept_code
            return self._internal_dept_cache.get(cache_key)

    # ─────────────────────────────────────────────────────────
    # 3. Fetch clinic queue progress
    # ─────────────────────────────────────────────────────────
    async def fetch_clinic_progress(
        self, room: str, period: str, **kwargs
    ) -> Optional[ClinicProgress]:
        """
        Query current calling number and clinic status from progressstatus.php.

        Endpoint (plain HTTP GET, no AJAX needed):
          https://www.hc.mmh.org.tw/progressstatus.php?dept={dept_code}&ap={period}

        period: '1'=上午診, '2'=下午診, '3'=夜間診

        回傳的 HTML 包含 <table class="regtable">，欄位為：
          位置 | 診別 | 醫師 | 目前看診號 | 未看診人數

        Note: room parameter 在馬偕系統中對應 dept (科別代碼)。
        """
        # Convert period to HMMH format if it's already a Chinese string
        if period in self.PERIOD_REVERSE_MAP:
            period = self.PERIOD_REVERSE_MAP[period]

        target_dept = room
        doctor_name = kwargs.get('doctor_name', '')
        dept_code = kwargs.get('dept_code', '')
        
        if dept_code and doctor_name:
            internal_code = await self._get_internal_dept_code(dept_code, doctor_name)
            if internal_code:
                log.info(f"[HMMH] Resolved internal dept_code {internal_code} for {doctor_name} (original room={room})")
                target_dept = internal_code

        url = f"{self.BASE_URL}/progressstatus.php"
        params = {"dept": target_dept, "ap": period}

        log.info(f"[HMMH] Fetching clinic progress: dept={target_dept}, ap={period}, kwargs={kwargs}")

        try:
            html = await self._get(url, params=params)
        except Exception as e:
            log.error(f"[HMMH] Error fetching clinic progress for dept={target_dept}, ap={period}: {e}")
            return None

        soup = BeautifulSoup(html, "lxml")

        # Check for global status ONLY if there is no regtable found
        page_text = soup.get_text()
        global_status = None
        if "尚未開始看診" in page_text and "regtable" not in html:
            global_status = "未開診"

        # Find the progress table (class="regtable")
        # Table columns: 位置 | 診別 | 醫師 | 目前看診號 | 未看診人數
        table = soup.find("table", class_=lambda x: x and "regtable" in x)

        if not table:
            log.warning(f"[HMMH] No regtable found for dept={room}, ap={period}")
            if global_status:
                # Return the status only (e.g. "已停診")
                return ClinicProgress(
                    clinic_room=room,
                    session_type=self.PERIOD_MAP.get(period, period),
                    current_number=0,
                    total_quota=0,
                    registered_count=0,
                    status=global_status,
                    waiting_list=[],
                    clinic_queue_details=[],
                )
            return None

        clinic_queue_details = []
        current_number = None
        total_waiting = 0
        doctor_status = None

        rows = table.find("tbody").find_all("tr") if table.find("tbody") else table.find_all("tr")[1:]
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 5:
                continue

            location = cells[0].get_text(strip=True)    # 位置 e.g. 福音樓 02樓
            clinic_name = cells[1].get_text(strip=True)  # 診別 e.g. 胃內01診
            doctor = cells[2].get_text(strip=True)       # 醫師 e.g. 陳重助
            current_no_text = cells[3].get_text(strip=True)  # 目前看診號 e.g. 88號或已停診
            waiting_text = cells[4].get_text(strip=True)     # 未看診人數 e.g. 5人

            kwargs_doctor = kwargs.get('doctor_name', '')
            if kwargs_doctor and kwargs_doctor not in doctor:
                continue

            # Parse status from the specific doctor's row
            if "已停診" in current_no_text or "停診" in current_no_text:
                doctor_status = "已停診"
            elif "未開診" in current_no_text or "尚未開始看診" in current_no_text:
                doctor_status = "未開診"
            elif "看診完畢" in current_no_text or "已結束看診" in current_no_text:
                doctor_status = "看診完畢"
                
            if not doctor_status:
                if "已停診" in waiting_text or "停診" in waiting_text:
                    doctor_status = "已停診"
                elif "未開診" in waiting_text or "尚未開始看診" in waiting_text:
                    doctor_status = "未開診"
                elif "看診完畢" in waiting_text or "已結束看診" in waiting_text:
                    doctor_status = "看診完畢"

            # Parse current calling number (remove 「號」)
            current_no = _parse_int(current_no_text)
            # Parse waiting count (remove 「人」)
            waiting_count = _parse_int(waiting_text)

            if current_no is not None:
                current_number = current_no  # Use last row if multiple clinics
            if waiting_count is not None:
                total_waiting += waiting_count

            clinic_queue_details.append({
                "location": location,
                "clinic_name": clinic_name,
                "doctor": doctor,
                "current_number": current_no,
                "waiting_count": waiting_count,
            })
            log.debug(f"[HMMH] Clinic row match: {clinic_name} 醫師={doctor} 看診號={current_no_text} 未看診={waiting_text}")

        if not clinic_queue_details and not doctor_status:
            log.warning(f"[HMMH] No data rows and no status for dept={room}, ap={period}")
            return None

        log.info(
            f"[HMMH] Clinic progress dept={room} ap={period}: "
            f"current={current_number}, waiting_total={total_waiting}, "
            f"rows={len(clinic_queue_details)}, status={doctor_status}"
        )

        return ClinicProgress(
            clinic_room=room,
            session_type=self.PERIOD_MAP.get(period, period),
            current_number=current_number or 0,
            total_quota=0,  # HMMH progressstatus.php does not expose total quota
            registered_count=total_waiting + (current_number or 0),  # estimate
            status=doctor_status,
            waiting_list=[],  # HMMH returns aggregate count, not individual numbers
            clinic_queue_details=clinic_queue_details,
        )

    # ─────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────
    def calculate_remaining_count(
        self,
        current_number: int,
        target_number: int,
        clinic_queue_details: list[dict],
    ) -> int:
        """
        計算 HMMH 的待看診人數。
        
        HMMH 的燈號狀態類似 CMUH，統計當前號碼到目標號碼之間的個數。
        
        Args:
            current_number: 目前正在看診的號碼
            target_number: 使用者的掛號號碼
            clinic_queue_details: 燈號清單，格式為 [{"number": 1, "status": "未看診"}, ...]
        
        Returns:
            還剩多少人未看診的數量
        """
        if not clinic_queue_details or current_number >= target_number:
            return 0
        
        # 統計 current_number < number < target_number 的號碼
        remaining = len([
            item for item in clinic_queue_details
            if item.get("number", 0) > current_number
            and item.get("number", 0) < target_number
        ])
        
        return remaining

    @staticmethod
    def _parse_date(text: str) -> Optional[date]:
        """Parse AD year format date: YYYY/MM/DD or YYYY-MM-DD"""
        text = text.strip()
        m = HMMHScraper.DATE_PATTERN.search(text)
        if m:
            try:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                pass
        return None

    @staticmethod
    def _normalize_session_type(text: str) -> str:
        """Normalize session type to standard format"""
        if "上午" in text or "morning" in text.lower() or "AM" in text:
            return "上午"
        if "下午" in text or "afternoon" in text.lower() or "PM" in text:
            return "下午"
        if "晚上" in text or "夜診" in text or "evening" in text.lower() or "night" in text.lower():
            return "晚上"
        return text.strip() or "上午"
