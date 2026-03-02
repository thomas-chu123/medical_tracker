"""
NTUH Hsinchu (國立臺灣大學醫學院附設醫院新竹分院) Scraper

Scrapes appointment schedule data from NTUH Hsinchu (新竹臺大分院).

Page structure:
  RegShowBlock?vHospCode=T4
    → Three category panels (內科系/外科系/其他科系), each with department links.
      Links format: RegDeptSchedule?vHospCode=T4&vDeptCode=MED&showBlock=A

  RegDeptSchedule?vHospCode=T4&vDeptCode=MED&showBlock=A
    → Department schedule page.
      Organized by date blocks containing period sub-sections (上午/下午/晚上),
      each period section containing doctor <button class="doctor-tag"> cards.
      Doctor name heading (h5) format: "醫師名 | 診室號 診 [狀態] 科別"
      Doctor IDs extracted from: RegDoctorInfo?vHospCode=T4&drID=H12345

  ClinicCurrentLightNo?vHospCode=T4
    → Current queue number query page.

Data flow:
  fetch_departments() → extract departments with category from RegShowBlock
  fetch_schedule(dept_code) → parse doctor slots from RegDeptSchedule
  fetch_clinic_progress(room, period) → query ClinicCurrentLightNo for real-time progress
"""

import asyncio
import re
from datetime import date, timedelta, datetime
from typing import Optional

import httpx
from bs4 import BeautifulSoup, Tag
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

# Category (showBlock) mapping
SHOW_BLOCK_NAMES = {
    "A": "內科系",
    "B": "外科系",
    "C": "其他科系",
}

PERIOD_MAP = {
    "上午": "上午",
    "下午": "下午",
    "晚上": "晚上",
    "夜間": "晚上",
    "黃昏": "下午",   # 黃昏門診 maps to 下午
}

PERIOD_CODE_MAP = {
    "上午": "1",
    "下午": "2",
    "晚上": "3",
}

# Regex patterns
DR_ID_RE = re.compile(r"drID=([A-Za-z0-9]+)")
DEPT_CODE_RE = re.compile(r"vDeptCode=([A-Za-z0-9]+).*?showBlock=([A-C])")
SHOW_BLOCK_RE = re.compile(r"showBlock=([A-C])")
CLINIC_ROOM_RE = re.compile(r"(\d{1,3})\s*診")
DATE_SLASH_RE = re.compile(r"(\d{1,2})/(\d{1,2})")  # e.g., 3/2


def _parse_int(text: Optional[str]) -> Optional[int]:
    """Extract first integer from a string."""
    if not text:
        return None
    m = re.search(r"\d+", text.strip())
    return int(m.group()) if m else None


def _resolve_date(month: int, day: int, ref_date: Optional[date] = None) -> date:
    """
    Resolve a (month, day) pair to a concrete date relative to ref_date.
    If the month/day has already passed this year, assume next year.
    """
    today = ref_date or date.today()
    try:
        candidate = date(today.year, month, day)
    except ValueError:
        return today
    # If the date is more than 30 days in the past, bump year
    if (today - candidate).days > 30:
        try:
            candidate = date(today.year + 1, month, day)
        except ValueError:
            pass
    return candidate


def _parse_period(text: str) -> Optional[str]:
    """Detect period from section label text."""
    for keyword, period in PERIOD_MAP.items():
        if keyword in text:
            return period
    return None


def _parse_doctor_h5(h5_text: str) -> tuple[str, Optional[str], Optional[str], bool]:
    """
    Parse a doctor h5 heading.

    Format examples:
      "謝慕揚 | 01 診 心臟血管科"
      "楊為舜 | 03 診 停診 腎臟科"
      "鄒秉諴 | 18 診 本院初診 胸腔科"

    Returns:
        (doctor_name, clinic_room, specialty, is_cancelled)
    """
    text = h5_text.strip()
    is_cancelled = "停診" in text

    # Split on " | " separator
    if " | " in text:
        parts = text.split(" | ", 1)
        doctor_name = parts[0].strip()
        right = parts[1].strip()  # e.g. "01 診 心臟血管科" or "03 診 停診 腎臟科"
    else:
        return text, None, None, is_cancelled

    # Extract clinic room number (first digits before 診)
    room_match = CLINIC_ROOM_RE.search(right)
    clinic_room = room_match.group(1) if room_match else None

    # Remove leading room+診 portion, then strip status keywords to get specialty
    right_stripped = CLINIC_ROOM_RE.sub("", right, count=1).strip()
    # Remove known status tokens
    for token in ("停診", "本院初診", "本院"):
        right_stripped = right_stripped.replace(token, "").strip()

    specialty = right_stripped if right_stripped else None

    return doctor_name, clinic_room, specialty, is_cancelled


class NTUHHsinchuScraper(BaseScraper):
    """
    Scraper for NTUH Hsinchu (國立臺灣大學醫學院附設醫院新竹分院).

    Hospital Code: NTUH_HSINCHU
    API HospCode: T4
    """

    HOSPITAL_CODE = "NTUH_HSINCHU"
    BASE_URL = "https://reg.ntuh.gov.tw/WebReg/WebReg"

    def __init__(self):
        super().__init__()
        self._client: Optional[httpx.AsyncClient] = None
        # Map dept_code → showBlock letter, populated during fetch_departments
        self._dept_block_map: dict[str, str] = {}
        # Cache for today's clinic list to avoid redundant parsing
        self._today_clinic_list_cache: list[dict] = []
        self._cache_timestamp: Optional[date] = None
        self._cache_expiry: Optional[datetime] = None
        self._cache: dict = {}
        self._cache_lock = asyncio.Lock()

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
        """
        Execute GET request with streaming to avoid malformed chunked encoding
        errors that occur on large NTUH pages (MED = 3.7 MB).
        """
        log.info(f"[NTUH] GET {url} params={kwargs.get('params')}")
        client = await self._get_client()
        # Use stream=True so we accumulate bytes incrementally and tolerate
        # the server's non-compliant chunked encoding footers.
        async with client.stream("GET", url, **kwargs) as resp:
            resp.raise_for_status()
            chunks: list[bytes] = []
            async for chunk in resp.aiter_bytes():
                chunks.append(chunk)
        content = b"".join(chunks).decode(resp.encoding or "utf-8", errors="replace")
        log.info(f"[NTUH] GET {url} → {len(content)} chars")
        return content

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _post(self, url: str, data: dict, **kwargs) -> str:
        """Execute POST request with retry logic."""
        log.info(f"[NTUH] POST {url} data keys={list(data.keys())} kwargs={kwargs}")
        client = await self._get_client()
        resp = await client.post(url, data=data, **kwargs)
        resp.raise_for_status()
        return resp.text

    # ─────────────────────────────────────────────────────────
    # 1. Fetch department list
    # ─────────────────────────────────────────────────────────
    async def fetch_departments(self) -> list[DepartmentData]:
        """
        Fetch department list from NTUH Hsinchu.

        Parses RegShowBlock HTML which contains three category panels:
          - 內科系 (showBlock=A)
          - 外科系 (showBlock=B)
          - 其他科系 (showBlock=C)

        Each panel contains <a> links to department schedule pages.

        Returns:
            list[DepartmentData]: Departments with code, name, category, hospital_code.
        """
        url = f"{self.BASE_URL}/RegShowBlock"
        html = await self._get(url, params={"vHospCode": "T4"})
        soup = BeautifulSoup(html, "html.parser")

        departments: list[DepartmentData] = []
        seen_codes: set[str] = set()
        sort_order = 1

        # Strategy 1: Look for category block containers (div with category title + dept links)
        # The page has sections for 內科系 / 外科系 / 其他科系
        # Each section's department links contain vDeptCode and showBlock params
        all_links = soup.find_all("a", href=True)

        for a in all_links:
            href = a.get("href", "")
            if "RegDeptSchedule" not in href:
                continue

            m = DEPT_CODE_RE.search(href)
            if not m:
                continue

            dept_code = m.group(1)
            show_block = m.group(2)

            if dept_code in seen_codes:
                continue

            dept_name = a.get_text(strip=True)
            if not dept_name:
                continue

            # Determine category from showBlock
            category = SHOW_BLOCK_NAMES.get(show_block, "其他科系")

            seen_codes.add(dept_code)
            self._dept_block_map[dept_code] = show_block

            departments.append(
                DepartmentData(
                    name=dept_name,
                    code=dept_code,
                    hospital_code=self.HOSPITAL_CODE,
                    category=category,
                    sort_order=sort_order,
                )
            )
            sort_order += 1

        log.info(f"[NTUH] Fetched {len(departments)} departments: {[d.code for d in departments]}")
        return departments

    # ─────────────────────────────────────────────────────────
    # 2. Fetch doctor slots for a department
    # ─────────────────────────────────────────────────────────
    async def fetch_schedule(self, dept_code: str) -> list[DoctorSlot]:
        """
        Fetch doctor schedule for a specific department from RegDeptSchedule.

        The schedule page contains date sections, each with period sub-sections
        (上午/下午/晚上), each containing doctor card entries.

        Doctor card h5 format: "醫師名 | 診室號 診 [狀態] 科別"
        Doctor ID from: RegDoctorInfo?vHospCode=T4&drID=H12345

        Args:
            dept_code: Department code (e.g., "MED", "SURG", "ORTH")

        Returns:
            list[DoctorSlot]: Doctor slots with schedule information.
        """
        log.info(f"[NTUH] fetch_schedule for dept={dept_code}")

        # Determine showBlock; if not cached from fetch_departments, try all blocks
        show_block = self._dept_block_map.get(dept_code)
        if not show_block:
            # Attempt to discover the correct showBlock by probing each panel.
            # Use a raw request (bypassing tenacity) so a 500 on the wrong block
            # is silently skipped rather than exhausting retries.
            client = await self._get_client()
            for block in ("A", "B", "C"):
                try:
                    resp = await client.get(
                        f"{self.BASE_URL}/RegDeptSchedule",
                        params={"vHospCode": "T4", "vDeptCode": dept_code, "showBlock": block},
                    )
                    if resp.status_code == 200 and len(resp.text) > 5000:
                        show_block = block
                        self._dept_block_map[dept_code] = block
                        log.info(f"[NTUH] dept={dept_code} discovered showBlock={block}")
                        break
                except Exception as e:
                    log.debug(f"[NTUH] Probe block={block} for dept={dept_code} failed: {e}")
                    continue
            if not show_block:
                show_block = "A"
                log.warning(f"[NTUH] Could not discover showBlock for dept={dept_code}, defaulting to A")

        url = f"{self.BASE_URL}/RegDeptSchedule"
        html = await self._get(
            url,
            params={"vHospCode": "T4", "vDeptCode": dept_code, "showBlock": show_block},
        )
        soup = BeautifulSoup(html, "html.parser")

        slots = await self._parse_schedule_page(soup, dept_code)
        log.info(f"[NTUH] fetch_schedule dept={dept_code}: {len(slots)} slots")
        return slots

    async def _fetch_doctor_slots(
        self, doctor_no: str, doctor_name: str, dept_code: str
    ) -> list[DoctorSlot]:
        """
        個別補足抓取特定醫師的排班時段。
        NTUH 做法：抓取該醫師所屬科別的完整課表，並過濾出目標醫師。
        """
        log.info(f"[NTUH] _fetch_doctor_slots for {doctor_name} ({doctor_no}) in dept={dept_code}")
        try:
            # 優先嘗試抓取傳入的 dept_code
            all_slots = await self.fetch_schedule(dept_code)
        except Exception as e:
            log.error(f"[NTUH] Error fetching schedule for dept={dept_code} during supplement: {e}")
            return []

        # 比對姓名或醫師編號
        matched = []
        for s in all_slots:
            if s.doctor_name == doctor_name or s.doctor_no == doctor_no:
                matched.append(s)
        
        log.info(f"[NTUH] Found {len(matched)} slots for {doctor_name} via dept scan")
        return matched

    async def _parse_schedule_page(
        self, soup: BeautifulSoup, dept_code: str
    ) -> list[DoctorSlot]:
        """
        Parse a RegDeptSchedule HTML page into DoctorSlot entries.

        Actual page structure (as of 2026-03):
          div.date-doctor-block#deptScheduleList
            div.row#deptScheduleResult
              div.col-1 (date column: "3/2" + "星期一")
              div.col-md-11 (schedule column)
                div.table-content
                  div.row (period group, yellow/blue bg)
                    div.col-12 → span.date "下午門診"  (period heading)
                    div.col-12.col-sm-6 id="N_doctorName"
                      button.doctor-tag
                        div.doc-name "呂紹宇 | 39 診"
                        div.btn.btn-secondary "老年醫學部 | 普通門診"

        All date rows share a single #deptScheduleResult wrapper with paired
        col-1 (date) and col-md-11 (schedule) children.

        Fallback strategies:
          B: h5 headings with surrounding date/period context
          C: global button.doctor-tag scan with _infer_date_period
        """
        slots: list[DoctorSlot] = []
        today = date.today()

        # ── Strategy A: walk #deptScheduleResult date/schedule column pairs ──
        slots.extend(self._parse_result_div(soup, dept_code, today))

        # ── Strategy B: parse h5 headings with context tracking ──────────────
        # Handles pages that render doctor entries as h5 headings
        if not slots:
            slots.extend(self._parse_h5_schedule(soup, dept_code, today))

        # ── Strategy C: global doctor-tag button scan ─────────────────────────
        if not slots:
            slots.extend(self._parse_doctor_tags(soup, dept_code, today))

        return slots

    def _parse_result_div(
        self,
        soup: BeautifulSoup,
        dept_code: str,
        today: date,
    ) -> list[DoctorSlot]:
        """
        Strategy A: Walk the actual NTUH schedule DOM.

        The page structure:
          #deptScheduleResult
            div.col-md-11
              div.table-content          ← one per date group
                div.sm-table-header      ← date label: "3/2(一), 老年醫學部"
                div.row (period group)
                  div.col-12 → span.date  ← period: "下午門診"
                  div.col-12.col-sm-6     ← doctor card wrapper
                    button.doctor-tag

        We iterate sm-table-header elements as date anchors, then scan
        the sibling row divs in order for period headings and buttons.
        """
        slots: list[DoctorSlot] = []
        result_div = soup.select_one("#deptScheduleResult")
        if not result_div:
            return slots

        schedule_col = result_div.select_one("div.col-md-11")
        if not schedule_col:
            return slots

        # Each table-content is one date group
        table_contents = schedule_col.find_all("div", class_="table-content", recursive=False)
        if not table_contents:
            # Some layouts nest table-content one level deeper
            table_contents = schedule_col.select("div.table-content")
        if not table_contents:
            return slots

        seen_btn_ids: set[int] = set()  # prevent duplicates from nested rows

        for tc in table_contents:
            # Date from sm-table-header: "3/2(一), 老年醫學部"
            sm_header = tc.find("div", class_="sm-table-header")
            session_date = today
            if sm_header:
                m = DATE_SLASH_RE.search(sm_header.get_text(strip=True))
                if m:
                    session_date = _resolve_date(int(m.group(1)), int(m.group(2)), today)

            # Period context — scan the direct children of tc in order
            current_period = "上午"

            # Walk only DIRECT child rows of tc (not recursive), to avoid
            # descending into modal pop-up divs that repeat the same buttons.
            direct_rows = tc.find_all("div", class_="row", recursive=False)
            # If no direct row children (page layout differs), fall one level deeper
            if not direct_rows:
                inner = tc.find("div", class_="row")
                direct_rows = inner.find_all("div", class_="row", recursive=False) if inner else []

            for row in direct_rows:
                # Period heading detection
                period_span = row.find("span", class_="date")
                if period_span:
                    detected = _parse_period(period_span.get_text(strip=True))
                    if detected:
                        current_period = detected

                # Doctor buttons — only DIRECT child col-divs to avoid modals
                col_divs = row.find_all("div", recursive=False)
                for col in col_divs:
                    for btn in col.find_all("button", class_=re.compile(r"doctor.?tag", re.I), recursive=False):
                        btn_id = id(btn)
                        if btn_id in seen_btn_ids:
                            continue
                        seen_btn_ids.add(btn_id)
                        doctor_slots = self._extract_doctor_tags(
                            col, dept_code, session_date, current_period
                        )
                        slots.extend(doctor_slots)
                        break  # one call per col is enough

        return slots

    def _extract_date_from_block(self, block: Tag, today: date) -> date:
        """Extract date from a date block element."""
        # Try date-header child
        for cls in ("date-header", "date-label", "date-title"):
            header = block.find(class_=re.compile(cls, re.I))
            if header:
                text = header.get_text(strip=True)
                m = DATE_SLASH_RE.search(text)
                if m:
                    return _resolve_date(int(m.group(1)), int(m.group(2)), today)

        # Try the block's own text
        block_text = block.get_text(separator=" ", strip=True)[:50]
        m = DATE_SLASH_RE.search(block_text)
        if m:
            return _resolve_date(int(m.group(1)), int(m.group(2)), today)

        return today

    def _extract_period_from_block(self, block: Tag) -> Optional[str]:
        """Detect period label from a block element."""
        # Try period-header child
        for cls in ("period-header", "time-label", "session-header", "period-title"):
            header = block.find(class_=re.compile(cls, re.I))
            if header:
                return _parse_period(header.get_text(strip=True))

        # Fall back to scanning block text
        block_text = block.get_text(separator=" ", strip=True)[:100]
        return _parse_period(block_text)

    def _extract_doctor_tags(
        self,
        container: Tag,
        dept_code: str,
        session_date: date,
        session_type: str,
    ) -> list[DoctorSlot]:
        """
        Extract DoctorSlot entries from button.doctor-tag elements within container.

        Actual button structure (NTUH Hsinchu 2026-03):
          <button class="doctor-tag avaliable|full|stopped">
            <div class="doc-name">呂紹宇 | 39 診</div>
            <div class="btn btn-secondary">老年醫學部 | 普通門診</div>
          </button>

        Button status classes: avaliable, full, stopped (typo on site).
        """
        slots: list[DoctorSlot] = []
        buttons = container.find_all("button", class_=re.compile(r"doctor.?tag", re.I))

        for btn in buttons:
            btn_classes = " ".join(btn.get("class", []))

            # ── Detect cancellation / full from button class ──────────
            is_cancelled = "stopped" in btn_classes
            is_full = "full" in btn_classes and "avaliable" not in btn_classes

            # ── Extract name/room from div.doc-name ───────────────────
            # Actual class used on NTUH site is 'doc-name', not 'doctor-name'
            name_div = (
                btn.find("div", class_="doc-name")
                or btn.find(class_=re.compile(r"doc.?name|doctor.?name", re.I))
            )

            if name_div:
                name_text = name_div.get_text(strip=True)
            else:
                # Fall back: use the whole button text up to first newline-like break
                # and strip the info portion (dept | clinic-type line)
                full_text = btn.get_text(separator="\n", strip=True)
                lines = [l.strip() for l in full_text.splitlines() if l.strip()]
                name_text = lines[0] if lines else ""

            if not name_text or " | " not in name_text:
                continue

            doctor_name, clinic_room, specialty, h5_cancelled = _parse_doctor_h5(name_text)
            is_cancelled = is_cancelled or h5_cancelled

            # ── Extract doctor ID from onclick URL ────────────────────
            doctor_id = self._extract_dr_id_from_element(btn)
            # Also check the enclosing col div id which may contain e.g. "1_呂紹宇"
            parent_col = btn.find_parent("div", id=re.compile(r"^\d+_"))
            if not doctor_id and parent_col:
                col_id = parent_col.get("id", "")
                # id format: "<scheduleNo>_<doctorName>"
                parts = col_id.split("_", 1)
                if len(parts) == 2 and parts[1]:
                    doctor_id = f"NTUH_T4_{parts[1]}"

            doctor_no = doctor_id or _make_doctor_no(doctor_name)

            # ── Build status string ───────────────────────────────────
            status_text: Optional[str] = None
            if is_cancelled:
                status_text = "停診"
            elif is_full:
                status_text = "額滿"

            slots.append(
                DoctorSlot(
                    doctor_no=doctor_no,
                    doctor_name=doctor_name,
                    department_code=dept_code,
                    session_date=session_date,
                    session_type=session_type,
                    total_quota=None,
                    registered=None,
                    clinic_room=clinic_room,
                    is_full=is_full,
                    status=status_text,
                )
            )

        return slots

    def _parse_h5_schedule(
        self, soup: BeautifulSoup, dept_code: str, today: date
    ) -> list[DoctorSlot]:
        """
        Fallback parser: walk h5 doctor headings and track surrounding date/period context.

        The page contains h5 elements like:
          <h5>謝慕揚 | 01 診 心臟血管科</h5>
          <a href="RegDoctorInfo?vHospCode=T4&drID=H11135">查看醫師所有門診</a>
          <a href="RegForm?newx=...">前往掛號</a>

        Date context is tracked from headings/labels that appear before the h5s.
        Period context is tracked similarly.
        """
        slots: list[DoctorSlot] = []
        current_date: date = today
        current_period: str = "上午"

        # Walk all meaningful elements in document order
        for elem in soup.descendants:
            if not isinstance(elem, Tag):
                continue

            tag = elem.name
            text = elem.get_text(strip=True)

            if not text:
                continue

            # Date detection: look for "M/D 星期X" patterns in headings/divs
            if tag in ("h2", "h3", "h4", "div", "span", "p", "th"):
                m = DATE_SLASH_RE.search(text)
                if m and len(text) < 30:
                    new_date = _resolve_date(int(m.group(1)), int(m.group(2)), today)
                    current_date = new_date
                    continue

            # Period detection
            if tag in ("h3", "h4", "h5", "div", "span", "p", "th"):
                period = _parse_period(text)
                if period and len(text) < 20:
                    current_period = period
                    continue

            # Doctor heading detection (h5 with " | " separator)
            if tag == "h5" and " | " in text:
                doctor_name, clinic_room, specialty, is_cancelled = _parse_doctor_h5(text)

                # Look for sibling/adjacent links for doctor ID and status
                doctor_id = None
                is_full = False
                has_reg_link = False

                parent = elem.parent
                if parent:
                    for sib in parent.find_all("a", href=True):
                        href = sib.get("href", "")
                        m_id = DR_ID_RE.search(href)
                        if m_id:
                            doctor_id = m_id.group(1)
                        if "RegForm" in href:
                            has_reg_link = True

                    # Check if any text in parent mentions 額滿
                    parent_text = parent.get_text(strip=True)
                    if "額滿" in parent_text or "掛滿" in parent_text:
                        is_full = True

                doctor_no = doctor_id or _make_doctor_no(doctor_name)

                status: Optional[str] = None
                if is_cancelled:
                    status = "停診"
                elif is_full:
                    status = "額滿"

                slots.append(
                    DoctorSlot(
                        doctor_no=doctor_no,
                        doctor_name=doctor_name,
                        department_code=dept_code,
                        session_date=current_date,
                        session_type=current_period,
                        total_quota=None,
                        registered=None,
                        clinic_room=clinic_room,
                        is_full=is_full,
                        status=status,
                    )
                )

        log.debug(f"[NTUH] _parse_h5_schedule dept={dept_code}: {len(slots)} slots")
        return slots

    def _parse_doctor_tags(
        self, soup: BeautifulSoup, dept_code: str, today: date
    ) -> list[DoctorSlot]:
        """
        Final fallback: find all button.doctor-tag globally and infer date/period
        from nearest preceding date/period heading via _infer_date_period.
        """
        slots: list[DoctorSlot] = []
        buttons = soup.find_all("button", class_=re.compile(r"doctor.?tag", re.I))
        if not buttons:
            buttons = soup.find_all("a", class_=re.compile(r"doctor.?tag", re.I))

        for btn in buttons:
            btn_classes = " ".join(btn.get("class", []))
            is_cancelled = "stopped" in btn_classes
            is_full = "full" in btn_classes and "avaliable" not in btn_classes

            # Try doc-name first, then generic regex
            name_div = (
                btn.find("div", class_="doc-name")
                or btn.find(class_=re.compile(r"doc.?name|doctor.?name", re.I))
            )
            if name_div:
                name_text = name_div.get_text(strip=True)
            else:
                full_text = btn.get_text(separator="\n", strip=True)
                lines = [l.strip() for l in full_text.splitlines() if l.strip()]
                name_text = lines[0] if lines else ""

            if not name_text or " | " not in name_text:
                continue

            doctor_name, clinic_room, specialty, h5_cancelled = _parse_doctor_h5(name_text)
            is_cancelled = is_cancelled or h5_cancelled

            session_date, session_type = self._infer_date_period(btn, today)

            doctor_id = self._extract_dr_id_from_element(btn)
            doctor_no = doctor_id or _make_doctor_no(doctor_name)

            status_text: Optional[str] = None
            if is_cancelled:
                status_text = "停診"
            elif is_full:
                status_text = "額滿"

            slots.append(
                DoctorSlot(
                    doctor_no=doctor_no,
                    doctor_name=doctor_name,
                    department_code=dept_code,
                    session_date=session_date,
                    session_type=session_type,
                    total_quota=None,
                    registered=None,
                    clinic_room=clinic_room,
                    is_full=is_full,
                    status=status_text,
                )
            )

        return slots

    def _infer_date_period(
        self, elem: Tag, today: date
    ) -> tuple[date, str]:
        """Walk up/back in DOM to find nearest date and period context."""
        session_date = today
        session_type = "上午"

        # Walk up ancestors looking for date/period info
        for ancestor in elem.parents:
            text = ancestor.get_text(separator=" ", strip=True)[:200]

            # Try to find date
            m = DATE_SLASH_RE.search(text)
            if m:
                session_date = _resolve_date(int(m.group(1)), int(m.group(2)), today)

            # Try to find period
            period = _parse_period(text)
            if period:
                session_type = period

            # Stop at body
            if ancestor.name in ("body", "html"):
                break

        return session_date, session_type

    def _extract_dr_id_from_element(self, elem: Tag) -> Optional[str]:
        """Find drID in onclick attribute or nearby anchor hrefs."""
        # Check onclick
        onclick = elem.get("onclick", "")
        m = DR_ID_RE.search(onclick)
        if m:
            return m.group(1)

        # Check data attributes
        for attr_val in elem.attrs.values():
            if isinstance(attr_val, str):
                m = DR_ID_RE.search(attr_val)
                if m:
                    return m.group(1)

        # Check child/sibling links
        parent = elem.parent
        if parent:
            for a in parent.find_all("a", href=True):
                m = DR_ID_RE.search(a["href"])
                if m:
                    return m.group(1)

        return None

    # ─────────────────────────────────────────────────────────
    # 3. Fetch today's clinic list (for progress tracking)
    # ─────────────────────────────────────────────────────────
    async def fetch_today_clinic_list(self, dept_code: str = "") -> list[dict]:
        """
        獲取今日診間列表。
        NTUH 做法：透過 AJAX 請求 DeptLightTable 獲得該科別的即時看診列表。
        """
        # 使用科別代碼作為緩存鍵
        cache_key = f"clinic_list_{dept_code}"
        now = now_tw()
        
        # 檢查緩存（需要加鎖防止競態）
        async with self._cache_lock:
            if cache_key in self._cache:
                data, expiry = self._cache[cache_key]
                if now < expiry:
                    log.info(f"[NTUH] Using cached clinic list for dept={dept_code!r} (expires at {expiry})")
                    return data

        log.info(f"[NTUH] Fetching clinic list via AJAX for dept={dept_code!r}")
        
        # 1. 先獲取頁面以取得最新的 RequestVerificationToken
        url = f"{self.BASE_URL}/ClinicCurrentLightNo"
        try:
            html_form = await self._get(url, params={"vHospCode": "T4"})
        except Exception as e:
            log.error(f"[NTUH] Failed to get ClinicCurrentLightNo form: {e}")
            return []

        soup_form = BeautifulSoup(html_form, "html.parser")
        token = ""
        # 找尋包含 DropListHosp 的 form 內的 token
        target_form = None
        for f in soup_form.find_all("form"):
            if f.find("select", {"id": "DropListHosp"}):
                target_form = f
                break
        
        container = target_form if target_form else soup_form
        for inp in container.find_all("input", {"name": "__RequestVerificationToken"}):
            token = inp.get("value", "")
            if token:
                break

        if not token:
            log.warning("[NTUH] Could not find __RequestVerificationToken for AJAX request")
            return []

        # 2. 發送 AJAX POST 請求
        ajax_url = f"{self.BASE_URL}/DeptLightTable"
        
        # 自動判定時段 (1:上午, 2:下午, 3:夜間)
        if now.hour < 12:
            ampm = "1"
        elif now.hour < 17:
            ampm = "2"
        else:
            ampm = "3"

        payload = {
            "__RequestVerificationToken": token,
            "vHospitalCode": "T4",
            "DeptCode": dept_code or "MED", # 若無科別，預設內科
            "RegionCode": "",
            "AmpmCode": ampm
        }
        
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
        }

        try:
            html_results = await self._post(ajax_url, payload, headers=headers)
        except Exception as e:
            log.error(f"[NTUH] AJAX request to DeptLightTable failed: {e}")
            return []

        # 3. 解析結果
        clinics = self._parse_clinic_list(html_results)
        
        # 4. 存入緩存 (5分鐘) - 需要加鎖防止競態
        if clinics:
            expiry = now + timedelta(minutes=5)
            async with self._cache_lock:
                self._cache[cache_key] = (clinics, expiry)
            # 為了向後相容
            self._today_clinic_list_cache = clinics
            self._cache_expiry = expiry
            log.info(f"[NTUH] Cached {len(clinics)} clinics for dept={dept_code}")
        
        return clinics

    def _parse_clinic_list(self, html: str) -> list[dict]:
        """
        解析 ClinicCurrentLightNo 結果頁的診間卡片。

        頁面卡片結構:
          <div class="clinic-card" onclick="...ServiceIDSE=7651238...">
            <div class="clinic-number">02 診</div>
            <div class="doctor-name">高健能</div>
            <div class="dept-name">普通門診</div>
            <div class="lightno-number">001</div>  ← 目前燈號（紅色）
          </div>

        也可能用 <a href="...ServiceIDSE=..."> 包裹。
        """
        soup = BeautifulSoup(html, "html.parser")
        results: list[dict] = []
        seen_ids: set[str] = set()

        SERVICE_RE = re.compile(r"ServiceIDSE=(\d+)", re.IGNORECASE)

        def _extract_service_id(tag) -> str | None:
            # Check onclick, href, and all attributes
            for attr in ("onclick", "href", "data-url"):
                val = tag.get(attr, "")
                if val:
                    m = SERVICE_RE.search(val)
                    if m:
                        return m.group(1)
            # Check all string attributes
            for val in tag.attrs.values():
                if isinstance(val, str):
                    m = SERVICE_RE.search(val)
                    if m:
                        return m.group(1)
            return None

        # Strategy A: look for clickable clinic cards or links with ServiceIDSE
        for card in soup.find_all(["div", "a", "li", "td", "span"]):
            service_id = _extract_service_id(card)
            if not service_id or service_id in seen_ids:
                continue

            text = card.get_text(separator=" ", strip=True)
            # Heuristic: clinic cards mention room "02 診"
            room_m = re.search(r"(\d{1,3})\s*診", text)
            if not room_m:
                continue

            # Skip common non-clinic links if any
            if any(k in text for k in ("我的最愛", "掛號連結", "回首頁")):
                continue

            room = room_m.group(1).zfill(2)
            doctor = ""
            dept = ""
            current_number = None

            # Try to extract doctor name from nested elements
            doc_el = card.find(class_=re.compile(r"(doctor|doc|lightno-doctor|lightno-name)", re.I))
            if doc_el:
                doctor = doc_el.get_text(strip=True)
            else:
                # Fallback: find text that looks like a name (not the room)
                parts = [p.strip() for p in text.split() if p.strip()]
                for p in parts:
                    if len(p) >= 2 and p != f"{room}診" and "診" not in p:
                        doctor = p
                        break

            # Try department
            dept_el = card.find(class_=re.compile(r"(dept|department|lightno-dept)", re.I))
            if dept_el:
                dept = dept_el.get_text(strip=True)

            # Try current light number (the red number shown on the card)
            for cls in ("lightno-number", "current-no", "now-no", "light-no"):
                el = card.find(class_=re.compile(cls, re.I))
                if el:
                    n = _parse_int(el.get_text(strip=True))
                    if n is not None:
                        current_number = n
                    break

            seen_ids.add(service_id)
            results.append({
                "service_id": service_id,
                "room": room,
                "doctor": doctor,
                "dept": dept,
                "current_number": current_number,
            })

        # Strategy B: scan all onclick/href for ServiceIDSE in case A found nothing
        if not results:
            for m in SERVICE_RE.finditer(html):
                sid = m.group(1)
                if sid not in seen_ids:
                    seen_ids.add(sid)
                    results.append({"service_id": sid, "room": "", "doctor": "", "dept": "", "current_number": None})

        log.info(f"[NTUH] _parse_clinic_list: found {len(results)} clinics")
        return results

    # ─────────────────────────────────────────────────────────
    # 4. Fetch clinic progress by ServiceIDSE (new API)
    # ─────────────────────────────────────────────────────────
    async def fetch_clinic_progress_by_service_id(
        self, service_id: str
    ) -> Optional[ClinicProgress]:
        """
        用 ServiceIDSE 抓取指定診間的即時看診進度。

        URL 格式: ClinicCurrentLightNoDetail?ServiceIDSE={id}&vHospitalCode=T4

        Args:
            service_id: 診間的 ServiceIDSE 數字（字串格式）

        Returns:
            ClinicProgress 物件，包含目前燈號、已叫最大號、預計叫號、掛號總數、燈號狀態列表。
        """
        log.info(f"[NTUH] fetch_clinic_progress_by_service_id service_id={service_id}")

        url = f"{self.BASE_URL}/ClinicCurrentLightNoDetail"
        try:
            html = await self._get(
                url,
                params={"ServiceIDSE": service_id, "vHospitalCode": "T4"},
            )
        except Exception as e:
            log.error(f"[NTUH] Failed to fetch ClinicCurrentLightNoDetail service_id={service_id}: {e}")
            return None

        return self._parse_clinic_progress_detail(html, service_id)

    def _parse_clinic_progress_detail(
        self, html: str, service_id: str = ""
    ) -> Optional[ClinicProgress]:
        """
        解析 ClinicCurrentLightNoDetail 頁面。

        HTML 結構 (2026-03):
          <div class="room-number">內科部 02診</div>

          <div class="now-number">
            目前燈號
            <div class="number">3</div>      ← 目前叫到的號碼（可能空白）
          </div>
          <div class="biggest-number">
            已叫最大號
            <div class="number">43</div>     ← 已叫過的最大號（可能空白）
          </div>
          <div class="next-number">
            預計叫號
            <div class="number">44</div>     ← 預計下一個叫到的號（可能空白）
          </div>

          <div class="progress-number">1未報到</div>   ← 每個掛號者
          <div class="progress-number">3已報到</div>
          <div class="progress-number">11已報到</div>  ← 已到院，等待看診
          <div class="progress-number">15已報到</div>
          ...

        狀態對應:
          未報到 → 尚未到院
          已報到 → 已到院，等待看診 (registered)
          看診中 → 正在診間 (current)
          初診   → 本院初診病患

        回傳 ClinicProgress:
          current_number  = 目前燈號
          total_quota     = max(所有號碼) ← 代表掛號總額（實際最大號）
          registered_count = 掛號人數（所有 progress-number 的數量）
          waiting_list    = 尚在等待的號碼列表（未報到＋已報到）
        """
        soup = BeautifulSoup(html, "html.parser")

        # ── 1. 診間名稱 ──────────────────────────────────────────
        room_div = soup.find("div", class_="room-number")
        room_text = room_div.get_text(strip=True) if room_div else ""
        # 從 "內科部 02診" 提取診間號碼
        room_match = CLINIC_ROOM_RE.search(room_text)
        clinic_room = room_match.group(1) if room_match else service_id

        # ── 2. 目前燈號（now-number > .number）──────────────────
        current_number: Optional[int] = None
        now_div = soup.find("div", class_="now-number")
        if now_div:
            num_div = now_div.find("div", class_="number")
            if num_div:
                current_number = _parse_int(num_div.get_text(strip=True))

        # ── 3. 已叫最大號（biggest-number > .number）────────────
        biggest_number: Optional[int] = None
        big_div = soup.find("div", class_="biggest-number")
        if big_div:
            num_div = big_div.find("div", class_="number")
            if num_div:
                biggest_number = _parse_int(num_div.get_text(strip=True))

        # ── 4. 預計叫號（next-number > .number）─────────────────
        next_number: Optional[int] = None
        next_div = soup.find("div", class_="next-number")
        if next_div:
            num_div = next_div.find("div", class_="number")
            if num_div:
                next_number = _parse_int(num_div.get_text(strip=True))

        # ── 5. 所有燈號狀態（div.progress-number）───────────────
        # 每個 div 的文字格式: "號碼" + "狀態文字"，例如 "3已報到"、"5未報到"
        # 需要拆分數字和狀態
        all_numbers: list[int] = []
        waiting_list: list[int] = []     # 未報到 + 已報到（還沒看診的）
        registered_numbers: list[int] = []  # 已報到（到院等待）
        clinic_queue_details: list[dict] = []

        for pn_div in soup.find_all("div", class_="progress-number"):
            text = pn_div.get_text(strip=True)
            if not text:
                continue

            # 拆分號碼和狀態：開頭為數字部分，其餘為狀態
            num_match = re.match(r"^(\d+)(.*)$", text)
            if not num_match:
                continue

            num = int(num_match.group(1))
            status_str = num_match.group(2).strip()

            all_numbers.append(num)
            clinic_queue_details.append({"number": num, "status": status_str})

            # 未看診者（未報到 = 未到院，已報到 = 到院等待）
            if status_str in ("未報到", "已報到", "看診中", "初診") and status_str != "看診中":
                waiting_list.append(num)
            if status_str == "已報到":
                registered_numbers.append(num)

        # ── 6. 狀態偵測 ──────────────────────────────────────────
        text_all = soup.get_text(separator=" ", strip=True)
        status: Optional[str] = None
        if "看診完畢" in text_all or "已結束" in text_all:
            status = "看診完畢"
        elif "未開診" in text_all or "尚未開始" in text_all:
            status = "未開診"
        elif "休診" in text_all or "停診" in text_all:
            status = "休診"

        # ── 7. 若完全無資料，回傳 None ───────────────────────────
        if current_number is None and biggest_number is None and not all_numbers and not status:
            log.debug(f"[NTUH] No progress data for service_id={service_id}")
            return None

        # total_quota：用所有號碼中的最大號，或已叫最大號
        total_quota = max(all_numbers) if all_numbers else biggest_number
        registered_count = len(all_numbers)  # 所有已掛號人數

        log.info(
            f"[NTUH] ClinicDetail service_id={service_id} room={clinic_room} "
            f"current={current_number} biggest={biggest_number} next={next_number} "
            f"total={registered_count} waiting={len(waiting_list)}"
        )

        return ClinicProgress(
            clinic_room=clinic_room,
            session_type="",      # 由呼叫端填入
            current_number=current_number or 0,
            total_quota=total_quota,
            registered_count=registered_count,
            status=status,
            waiting_list=waiting_list,
            clinic_queue_details=clinic_queue_details,
        )

    # ─────────────────────────────────────────────────────────
    # 5. Fetch clinic progress (舊介面，向後相容)
    # ─────────────────────────────────────────────────────────
    async def fetch_clinic_progress(
        self, room: str, period: str, service_id: str = "", **kwargs
    ) -> Optional[ClinicProgress]:
        """
        抓取診間即時看診進度。

        優先使用 ServiceIDSE（新 API），若無則嘗試從今日列表頁比對診間號碼。

        Args:
            room:       診間號碼，例如 "02"、"1"
            period:     時段 "1"=上午, "2"=下午, "3"=晚上
            service_id: 若已知 ServiceIDSE 可直接傳入（效率較高）
            **kwargs:   支援傳入 dept_code 以提高查詢準確度（台大必須）

        Returns:
            Optional[ClinicProgress]
        """
        log.info(f"[NTUH] fetch_clinic_progress room={room} period={period} service_id={service_id!r} kwargs={kwargs}")

        # ── 若已有 ServiceIDSE，直接查詢 Detail 頁 ──────────────
        if service_id:
            result = await self.fetch_clinic_progress_by_service_id(service_id)
            if result:
                period_name_map = {"1": "上午", "2": "下午", "3": "晚上"}
                result.session_type = period_name_map.get(period, period)
                return result

        # ── 若無 ServiceIDSE：從今日列表頁找對應診間 ─────────────
        dept_code = kwargs.get("dept_code", "")
        log.info(f"[NTUH] No service_id, fetching clinic list to find room={room} (dept_code={dept_code!r})")
        try:
            clinic_list = await self.fetch_today_clinic_list(dept_code)
        except Exception as e:
            log.error(f"[NTUH] Failed to fetch clinic list: {e}")
            return None

        # 比對診間號碼（去除前置零，例如 "02" vs "2"）
        room_norm = str(int(room)) if room.isdigit() else room
        matched_sid = None
        for clinic in clinic_list:
            c_room = clinic.get("room", "")
            c_room_norm = str(int(c_room)) if c_room.isdigit() else c_room
            if c_room_norm == room_norm:
                matched_sid = clinic.get("service_id")
                break

        if not matched_sid:
            log.warning(f"[NTUH] Cannot find ServiceIDSE for room={room} in today's clinic list")
            return None

        result = await self.fetch_clinic_progress_by_service_id(matched_sid)
        if result:
            period_name_map = {"1": "上午", "2": "下午", "3": "晚上"}
            result.session_type = period_name_map.get(period, period)
        return result

    def _parse_clinic_progress(
        self, html: str, room: str, period: str
    ) -> Optional[ClinicProgress]:
        """
        舊版解析方法（保留相容性，現已委派給 _parse_clinic_progress_detail）。
        """
        result = self._parse_clinic_progress_detail(html, room)
        if result:
            period_name_map = {"1": "上午", "2": "下午", "3": "晚上"}
            result.session_type = period_name_map.get(period, period)
            result.clinic_room = room
        return result


# ─────────────────────────────────────────────────────────
# Utility helpers
# ─────────────────────────────────────────────────────────

def _make_doctor_no(doctor_name: str) -> str:
    """Generate a stable doctor_no from the doctor's name when no ID is available."""
    return re.sub(r"[^\w]", "", doctor_name)[:12]

