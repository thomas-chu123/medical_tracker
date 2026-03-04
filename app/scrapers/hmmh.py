"""
HMMH (馬偕紀念醫院新竹分院) Scraper

Scrapes:
1. /department.php                                    → department list (from select[name=depid])
2. /register_divide.php?depid={code}                  → doctor schedules for department (使用 Selenium)
3. /progressstatus.php?dept={dept}&ap={period}        → clinic progress

說明：馬偕醫院使用動態前端（JavaScript AJAX），因此需要 Selenium 來執行 JavaScript 並等待內容加載。
"""

import asyncio
import re
from datetime import date, datetime, timedelta
from typing import Optional
import time

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

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
        self._driver: Optional[webdriver.Chrome] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=HEADERS,
                timeout=settings.request_timeout,
                follow_redirects=True,
            )
        return self._client

    def _get_driver(self) -> webdriver.Chrome:
        """Get or create a Selenium WebDriver instance (non-async)"""
        if self._driver is None:
            chrome_options = ChromeOptions()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option("useAutomationExtension", False)
            
            try:
                # Try to use locally installed Chrome first
                service = Service(ChromeDriverManager().install())
                self._driver = webdriver.Chrome(service=service, options=chrome_options)
            except Exception as e:
                log.warning(f"[HMMH] Failed to use ChromeDriverManager: {e}, trying system Chrome")
                try:
                    # Fallback to system Chrome
                    self._driver = webdriver.Chrome(options=chrome_options)
                except Exception as e2:
                    log.error(f"[HMMH] Failed to initialize ChromeDriver: {e2}")
                    raise
            
            self._driver.implicitly_wait(10)
            log.info("[HMMH] Selenium WebDriver initialized")
        return self._driver

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
        if self._driver:
            self._driver.quit()
            self._driver = None
            log.info("[HMMH] Selenium WebDriver closed")

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
        Scrape department list from department.php
        
        頁面包含 <select name="depid"> 選擇框，包含所有科別。
        我們從該 select 元素提取所有 option，並將其轉換為 DepartmentData。
        depid 值為 1-15，代表不同的科別（內科部、外科部等）。
        """
        url = f"{self.BASE_URL}/department.php"
        html = await self._get(url)
        soup = BeautifulSoup(html, "lxml")

        departments: list[DepartmentData] = []

        # Find the select element with name="depid"
        select = soup.find("select", {"name": "depid"})
        if not select:
            log.warning("[HMMH] Could not find select[name=depid] element in department.php")
            return departments

        # Extract all options from the select element
        options = select.find_all("option")
        log.info(f"[HMMH] Found {len(options)} options in depid select")

        current_sort_order = 1
        for option in options:
            code = option.get("value", "").strip()
            name = option.get_text(strip=True)

            # Skip empty values (like "全部科別" with empty value)
            if not code or not name:
                log.debug(f"[HMMH] Skipping empty option: code='{code}', name='{name}'")
                continue

            # Skip non-numeric codes (safety check)
            if not code.isdigit():
                log.debug(f"[HMMH] Skipping non-numeric code: '{code}' for '{name}'")
                continue

            # Skip administrative/non-clinical departments
            skip_keywords = ["行政", "教學", "認證", "單位", "專案"]
            if any(keyword in name for keyword in skip_keywords):
                log.debug(f"[HMMH] Skipping non-clinical department: {name}")
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

        log.info(f"[HMMH] Found {len(departments)} departments")
        return departments

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
        Scrape doctor schedule for a specific department using Selenium.
        
        馬偕醫院的 register_divide.php 使用動態前端（AJAX），需要執行 JavaScript。
        此方法嘗試使用 Selenium，如果失敗則返回空列表。
        
        注意：當前實現是初步版本。由於馬偕前端是動態的，完整的醫生列表需要：
        1. Selenium 或 Playwright 等瀏覽器自動化工具
        2. 或通過逆向工程找到後端 API
        3. 或等待馬偕提供公開 API
        """
        log.info(f"[HMMH] fetch_schedule for dept_code={dept_code}")
        
        try:
            driver = self._get_driver()
        except Exception as e:
            log.warning(f"[HMMH] Cannot initialize Selenium WebDriver: {e}")
            log.info("[HMMH] Falling back to HTTP-only mode (no JavaScript execution)")
            return await self._fetch_schedule_http_fallback(dept_code)
        
        try:
            # 構建 URL
            url = f"{self.BASE_URL}/register_divide.php?depid={dept_code}"
            
            # 在 Selenium 中打開頁面
            driver.get(url)
            log.info(f"[HMMH] Opened {url}")
            
            # 等待 jQuery 加載
            try:
                WebDriverWait(driver, 10).until(
                    lambda d: d.execute_script("return typeof jQuery !== 'undefined'")
                )
                log.debug("[HMMH] jQuery loaded")
            except Exception as e:
                log.warning(f"[HMMH] jQuery loading timeout: {e}")
            
            # 等待表格加載
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.ID, "tblSch"))
                )
                log.debug("[HMMH] Table #tblSch found")
            except Exception as e:
                log.warning(f"[HMMH] Timeout waiting for table: {e}")
            
            # 主動執行 timetable() AJAX 調用
            # 使用當前日期作為 rundate 參數（格式: YYYYMMDD）
            try:
                today = date.today()
                rundate_str = today.strftime("%Y%m%d")
                
                # 執行 JavaScript 來調用 timetable(rundate)
                # 這會觸發 AJAX 請求並填充表格
                js_code = f"""
                if (typeof timetable === 'function') {{
                    return new Promise((resolve) => {{
                        timetable('{rundate_str}');
                        // 等待 AJAX 完成
                        setTimeout(resolve, 3000);
                    }});
                }} else {{
                    console.error('timetable function not found');
                    return false;
                }}
                """
                
                result = driver.execute_script(js_code)
                log.info(f"[HMMH] Executed timetable('{rundate_str}')")
                
                # 再等幾秒讓 AJAX 響應
                time.sleep(3)
                
            except Exception as e:
                log.warning(f"[HMMH] Error executing timetable() function: {e}")
            
            # 獲取當前頁面的 HTML（應該已包含 AJAX 響應的內容）
            page_html = driver.page_source
            
            # 解析 HTML
            soup = BeautifulSoup(page_html, "lxml")
            slots: list[DoctorSlot] = []
            
            # 查找表格
            tables = soup.find_all("table")
            log.debug(f"[HMMH] Found {len(tables)} tables on rendered page")
            
            if not tables:
                log.warning(f"[HMMH] No tables found on page after Selenium rendering")
                return slots
            
            # 處理表格
            for table in tables:
                rows = table.find_all("tr")
                if len(rows) < 2:
                    continue
                
                # 計算當週日期
                today = date.today()
                days_since_monday = today.weekday()
                week_start = today - timedelta(days=days_since_monday)
                
                # 尋找時段標籤行
                for row_idx, row in enumerate(rows[1:], start=1):
                    cells = row.find_all(["td", "th"])
                    if not cells:
                        continue
                    
                    first_cell = cells[0].get_text(strip=True)
                    
                    # 檢查是否為時段標籤
                    if first_cell in ["上午", "下午", "晚上"]:
                        session_type = first_cell
                        
                        # 遍歷該行中的醫生單元格
                        for col_idx, cell in enumerate(cells[1:]):
                            doctor_text = cell.get_text(strip=True)
                            
                            if not doctor_text or len(doctor_text) < 2:
                                continue
                            
                            # 解析醫生信息
                            doctor_info = self._parse_doctor_info(doctor_text)
                            if not doctor_info:
                                continue
                            
                            # 計算日期
                            if col_idx < 6:  # 週一到週六
                                slot_date = week_start + timedelta(days=col_idx)
                                
                                slot = DoctorSlot(
                                    doctor_no=doctor_info.get("code"),
                                    doctor_name=doctor_info.get("name"),
                                    department_code=dept_code,
                                    session_date=slot_date,
                                    session_type=session_type,
                                    total_quota=None,
                                    registered=None,
                                    clinic_room=None,
                                    is_full=False,
                                )
                                slots.append(slot)
                                log.debug(f"[HMMH] Added slot: {doctor_info.get('name')} on {slot_date} {session_type}")
            
            log.info(f"[HMMH] Found {len(slots)} doctor slots for dept_code={dept_code}")
            return slots
            
        except Exception as e:
            log.error(f"[HMMH] Error in fetch_schedule with Selenium: {e}", exc_info=True)
            return []

    async def _fetch_schedule_http_fallback(self, dept_code: str) -> list[DoctorSlot]:
        """
        Fallback method: Try to fetch schedule using HTTP only (no JavaScript).
        This will likely return fewer results since the page is dynamic.
        """
        log.info(f"[HMMH] Using HTTP fallback for dept_code={dept_code}")
        
        try:
            url = f"{self.BASE_URL}/register_divide.php"
            html = await self._get(url, params={"depid": dept_code})
            
            soup = BeautifulSoup(html, "lxml")
            slots: list[DoctorSlot] = []
            
            # In HTTP-only mode, we'll get mostly empty tables
            # This is expected since the content is loaded dynamically
            tables = soup.find_all("table")
            if not tables:
                log.warning(f"[HMMH] No tables found in HTTP response for dept_code={dept_code}")
                log.info("[HMMH] Doctor schedule requires JavaScript rendering")
                log.info("[HMMH] Future improvement: Integrate Playwright or fully headless Chrome")
            
            log.info(f"[HMMH] HTTP fallback found {len(slots)} doctor slots (expected: 0)")
            return slots
            
        except Exception as e:
            log.error(f"[HMMH] Error in HTTP fallback: {e}")
            return []

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
