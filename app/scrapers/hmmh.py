"""
HMMH (馬偕紀念醫院新竹分院) Scraper

Scrapes:
1. /find_division.php                                 → department list
2. /register_divide.php?depid={code}                  → doctor schedules (需要進一步分析)
3. /progressstatus.php?dept={dept}&ap={period}        → clinic progress
"""

import asyncio
import re
from datetime import date, datetime, timedelta
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
        log.info(f"[HMMH] GET {url} with params {kwargs.get('params')}")
        client = await self._get_client()
        resp = await client.get(url, **kwargs)
        resp.raise_for_status()
        log.info(f"[HMMH] GET {url} success ({len(resp.text)} chars)")
        return resp.text

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _post(self, url: str, data: dict) -> str:
        log.info(f"[HMMH] POST {url} with data {data}")
        client = await self._get_client()
        resp = await client.post(url, data=data)
        resp.raise_for_status()
        return resp.text

    # ─────────────────────────────────────────────────────────
    # 1. Fetch department list
    # ─────────────────────────────────────────────────────────
    async def fetch_departments(self) -> list[DepartmentData]:
        """
        Scrape department list from find_division.php
        
        頁面包含多個科室連結，每個連結的格式為：
        <a href='register_divide.php?depid=14'>一般外科</a>
        """
        url = f"{self.BASE_URL}/find_division.php"
        html = await self._get(url)
        soup = BeautifulSoup(html, "lxml")

        departments: list[DepartmentData] = []
        current_sort_order = 1

        # Find all links with 'depid' parameter
        for a in soup.find_all("a", href=True):
            href = a["href"]
            
            # Match pattern: depid=XX (any URL with depid parameter)
            m = self.DEPT_CODE_PATTERN.search(href)
            if not m:
                continue
            
            code = m.group(1)
            name = a.get_text(strip=True)
            
            # Filter: valid department names (at least 2 characters)
            if not name or len(name) < 2:
                log.debug(f"[HMMH] Skipping invalid department name: '{name}'")
                continue
            
            # Skip children's hospital (separate system)
            if "/child/" in href.lower():
                log.debug(f"[HMMH] Skipping children's hospital: {name}")
                continue
            
            # Skip single-doctor clinics
            if "register_single_doctor.php" in href.lower():
                log.debug(f"[HMMH] Skipping single-doctor clinic: {name}")
                continue
            
            departments.append(
                DepartmentData(
                    name=name,
                    code=code,
                    hospital_code=self.HOSPITAL_CODE,
                    category=self._categorize_department(name),
                    sort_order=current_sort_order
                )
            )
            log.debug(f"[HMMH] Added dept: code={code}, name={name}")
            current_sort_order += 1
        
        # Deduplicate by code (keep first occurrence)
        seen = set()
        unique: list[DepartmentData] = []
        for d in departments:
            if d.code not in seen:
                seen.add(d.code)
                unique.append(d)
        
        log.info(f"[HMMH] Found {len(unique)} unique departments")
        return unique

    @staticmethod
    def _categorize_department(name: str) -> str:
        """Categorize department based on name"""
        category_map = {
            # 內科系
            "一般內科": "內科系",
            "神經內科": "內科系",
            "心臟內科": "內科系",
            "心臟血管內科": "內科系",
            "胸腔內科": "內科系",
            "腸胃肝膽內科": "內科系",
            "消化內科": "內科系",
            "腎臟內科": "內科系",
            "風濕免疫科": "內科系",
            "過敏免疫風濕科": "內科系",
            "新陳代謝科": "內科系",
            "內分泌新陳代謝科": "內科系",
            "感染科": "內科系",
            "家庭醫學科": "內科系",
            "精神科": "內科系",
            "血液腫瘤科": "內科系",
            
            # 外科系
            "一般外科": "外科系",
            "神經外科": "外科系",
            "心臟血管外科": "外科系",
            "胸腔外科": "外科系",
            "大腸直腸外科": "外科系",
            "整形外科": "外科系",
            "美容門診": "外科系",
            "泌尿科": "外科系",
            "骨科": "外科系",
            "乳房外科": "外科系",
            "減重暨代謝手術門診": "外科系",
            "外傷科": "外科系",
            
            # 婦兒科系
            "婦產科": "婦兒科系",
            "兒科": "婦兒科系",
            
            # 其他專科
            "眼科": "其他專科",
            "耳鼻喉科": "其他專科",
            "牙科": "其他專科",
            "復健科": "其他專科",
            "皮膚科": "其他專科",
            "中醫科": "其他專科",
            "放射腫瘤科": "其他專科",
        }
        
        return category_map.get(name, "其他專科")

    # ─────────────────────────────────────────────────────────
    # 2. Fetch doctor slots for a department
    # ─────────────────────────────────────────────────────────
    async def fetch_schedule(self, dept_code: str) -> list[DoctorSlot]:
        """
        Scrape doctor schedule for a specific department
        
        URL: register_divide.php?depid={dept_code}
        """
        log.info(f"[HMMH] fetch_schedule for dept_code={dept_code}")
        url = f"{self.BASE_URL}/register_divide.php"
        html = await self._get(url, params={"depid": dept_code})
        
        soup = BeautifulSoup(html, "lxml")
        slots: list[DoctorSlot] = []
        
        # 找到表格 - 嘗試多種選擇器方式
        tables = soup.find_all("table")
        log.debug(f"[HMMH] Found {len(tables)} tables on page")
        
        for table_idx, table in enumerate(tables):
            log.debug(f"[HMMH] Processing table {table_idx}")
            rows = table.find_all("tr")
            
            if len(rows) < 3:
                log.debug(f"[HMMH] Table {table_idx} has only {len(rows)} rows, skipping")
                continue
            
            log.debug(f"[HMMH] Table {table_idx} has {len(rows)} rows")
            
            # 計算當週日期
            today = date.today()
            days_since_monday = today.weekday()
            week_start = today - timedelta(days=days_since_monday)
            log.debug(f"[HMMH] Week start: {week_start}")
            
            # 遍歷所有行
            for row_idx, row in enumerate(rows):
                cells = row.find_all(["td", "th"])
                
                if not cells or len(cells) < 2:
                    continue
                
                # 第一單元格應該是診間號或時段標籤
                first_cell_text = cells[0].get_text(strip=True)
                
                # 診間號應該是數字
                if first_cell_text.isdigit():
                    clinic_room = first_cell_text
                    log.debug(f"[HMMH] Found clinic room: {clinic_room}")
                    
                    # 遍歷該行的時段單元格
                    for col_idx, cell in enumerate(cells[1:]):
                        cell_text = cell.get_text(strip=True)
                        
                        if not cell_text or len(cell_text) < 2:
                            continue
                        
                        # 嘗試解析醫生信息
                        doctor_info = self._parse_doctor_info(cell_text)
                        if not doctor_info:
                            continue
                        
                        doctor_name = doctor_info.get("name")
                        doctor_no = doctor_info.get("code")
                        
                        # 計算日期和時段
                        day_idx = col_idx // 3
                        period_idx = col_idx % 3
                        
                        if day_idx >= 6:
                            continue
                        
                        slot_date = week_start + timedelta(days=day_idx)
                        session_type = self.PERIOD_MAP.get(str(period_idx + 1), "上午")
                        
                        slot = DoctorSlot(
                            doctor_no=doctor_no,
                            doctor_name=doctor_name,
                            department_code=dept_code,
                            session_date=slot_date,
                            session_type=session_type,
                            total_quota=None,
                            registered=None,
                            clinic_room=clinic_room,
                            is_full=False,
                        )
                        slots.append(slot)
                        log.debug(f"[HMMH] Added slot: {doctor_name}({doctor_no}) @ {slot_date} {session_type} clinic {clinic_room}")
        
        log.info(f"[HMMH] Found {len(slots)} total doctor slots for dept_code={dept_code}")
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

    # ─────────────────────────────────────────────────────────
    # 3. Fetch clinic queue progress
    # ─────────────────────────────────────────────────────────
    async def fetch_clinic_progress(
        self, room: str, period: str
    ) -> Optional[ClinicProgress]:
        """
        Query current calling number and clinic status
        
        URL: progressstatus.php?dept={dept_code}&ap={period}
        period: '1'=上午, '2'=下午, '3'=晚上
        
        Note: room parameter 在馬偕系統中對應到 dept (科別代碼)
        """
        # Convert period to HMMH format if it's already a Chinese string
        if period in self.PERIOD_REVERSE_MAP:
            period = self.PERIOD_REVERSE_MAP[period]
        
        url = f"{self.BASE_URL}/progressstatus.php"
        params = {"dept": room, "ap": period}
        
        log.info(f"[HMMH] Fetching clinic progress: dept={room}, ap={period}")
        
        try:
            html = await self._get(url, params=params)
        except Exception as e:
            log.error(f"[HMMH] Error fetching clinic progress for dept={room}, ap={period}: {e}")
            return None

        soup = BeautifulSoup(html, "lxml")
        
        # Look for tables with class 'regtable' or 'resp-table'
        tables = soup.find_all("table", class_=lambda x: x and ("regtable" in x or "resp-table" in x))
        
        if not tables:
            log.warning(f"[HMMH] No progress table found for dept={room}, ap={period}")
            return None
        
        # Parse the progress table
        current_number = None
        status = None
        numbers = []
        waiting_list = []
        clinic_queue_details = []
        
        # Extract text to check for status messages
        page_text = soup.get_text()
        
        if "已停診" in page_text:
            status = "已停診"
        elif "未開診" in page_text or "尚未開始看診" in page_text:
            status = "未開診"
        elif "看診完畢" in page_text or "已結束看診" in page_text:
            status = "看診完畢"
        
        # Parse table rows to extract patient numbers and statuses
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all("td")
                if len(cells) >= 2:
                    # First column: patient number
                    # Second column: status (未看診, 看診中, 已看診, etc.)
                    num_text = cells[0].get_text(strip=True)
                    status_text = cells[1].get_text(strip=True)
                    
                    num = _parse_int(num_text)
                    if num is not None and num_text.isdigit():
                        numbers.append(num)
                        clinic_queue_details.append({
                            "number": num,
                            "status": status_text
                        })
                        
                        # Build waiting list (patients not yet seen)
                        if "未看診" in status_text or "等候" in status_text:
                            waiting_list.append(num)
                        
                        # Track current calling number (看診中)
                        if "看診中" in status_text:
                            current_number = num
        
        # If no current number found but have data, use max number seen
        if current_number is None and numbers:
            # Find the last patient that's been called (not "未看診")
            for detail in reversed(clinic_queue_details):
                if "未看診" not in detail["status"]:
                    current_number = detail["number"]
                    break
        
        max_num = max(numbers) if numbers else 0
        registered_count = len(numbers)
        
        log.info(f"[HMMH] Clinic progress for dept={room}: current={current_number}, "
                f"total={max_num}, registered={registered_count}, waiting={len(waiting_list)}, status={status}")
        
        if current_number is None and not status and not numbers:
            return None
        
        return ClinicProgress(
            clinic_room=room,  # dept code
            session_type=self.PERIOD_MAP.get(period, period),
            current_number=current_number or 0,
            total_quota=max_num,
            registered_count=registered_count,
            status=status,
            waiting_list=waiting_list,
            clinic_queue_details=clinic_queue_details
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
