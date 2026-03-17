import asyncio
import re
from datetime import date, datetime
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_fixed, wait_exponential

from app.scrapers.base import BaseScraper, ClinicProgress, DepartmentData, DoctorSlot
from app.core.logger import logger


class TVGHTaichungScraper(BaseScraper):
    HOSPITAL_CODE = "TVGH_TAICHUNG"
    BASE_URL = "https://register.vghtc.gov.tw"

    def __init__(self):
        self.client = httpx.AsyncClient(
            verify=False,
            timeout=15.0,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        )

    async def close(self):
        await self.client.aclose()

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def fetch_departments(self) -> list[DepartmentData]:
        url = f"{self.BASE_URL}/register/listSection.jsp"
        resp = await self.client.get(url)
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        departments = []
        current_category = None
        
        for tr in soup.find_all('tr'):
            th = tr.find('th')
            if th and th.get('colspan'):
                category = th.text.strip()
                if category:
                    current_category = category
                    
            for link in tr.find_all('a'):
                href = link.get('href', '')
                if 'listDoctor.jsp' in href:
                    match = re.search(r'(?:section|§ion)=([A-Z0-9_]+)', href)
                    if match:
                        code = match.group(1)
                        name = link.text.strip()
                        if name and code:
                            departments.append(DepartmentData(
                                name=name,
                                code=code,
                                category=current_category,
                                hospital_code=self.HOSPITAL_CODE
                            ))
        
        unique_depts = {d.code: d for d in departments}
        return list(unique_depts.values())

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def fetch_schedule(self, dept_code: str) -> list[DoctorSlot]:
        url = f"{self.BASE_URL}/register/listDoctor.jsp"
        params = {"init": "sub", "section": dept_code}
        resp = await self.client.get(url, params=params)
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        doctors = []
        for a in soup.find_all('a'):
            onclick = a.get('onclick', '')
            if 'showDoc' in onclick:
                parts = onclick.split("'")
                if len(parts) >= 9:
                    drno = parts[1]
                    dept = parts[3]
                    drname = parts[5]
                    dept_name = parts[7]
                    doctors.append((drno, drname, dept_name))
            
        for div in soup.find_all('div', class_='doc'):
            onclick = div.get('onclick', '')
            if 'showDoc' in onclick:
                parts = onclick.split("'")
                if len(parts) >= 9:
                    drno = parts[1]
                    drname = parts[5]
                    dept_name = parts[7]
                    doctors.append((drno, drname, dept_name))

        docs = list(set(doctors))
        
        tasks = [self._fetch_doctor_slots(drno, drname, dept_code) for drno, drname, dept_name in docs]
        results = await asyncio.gather(*tasks)
        
        slots = []
        for doc_slots in results:
            slots.extend(doc_slots)
            
        return slots

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _fetch_doctor_slots(self, drno: str, drname: str, dept_code: str) -> list[DoctorSlot]:
        url = f"{self.BASE_URL}/register/doctor_schedule.jsp"
        params = {
            "init": "sub",
            "section": dept_code,
            "drno": drno,
            "drname": drname,
            "sectionname": ""
        }
        resp = await self.client.get(url, params=params)
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        slots = []
        
        for form in soup.find_all('form'):
            date_input = form.find('input', {'name': 'consultDateAD'})
            room_input = form.find('input', {'name': 'consultRoom'})
            noon_input = form.find('input', {'name': 'consultNoonFlag'})
            
            if not (date_input and room_input and noon_input):
                continue
                
            date_str = date_input.get('value')
            if not date_str or len(date_str) != 8:
                continue
                
            try:
                session_date = datetime.strptime(date_str, "%Y%m%d").date()
            except ValueError:
                continue
                
            noon_flag = noon_input.get('value', '').upper()
            if noon_flag == 'A':
                session_type = '上午'
            elif noon_flag == 'P':
                session_type = '下午'
            elif noon_flag in ('N', 'E'):
                session_type = '晚上'
            else:
                session_type = '上午'
                
            room = room_input.get('value', '').strip()
            
            registered = 0
            is_full = False
            
            div = form.find_parent('div')
            if div:
                text = div.text.strip()
                match = re.search(r'已掛人數[：:]\s*(\d+)', text)
                if match:
                    registered = int(match.group(1))
                if '額滿' in text:
                    is_full = True
            
            slots.append(DoctorSlot(
                doctor_no=drno,
                doctor_name=drname,
                department_code=dept_code,
                session_date=session_date,
                session_type=session_type,
                total_quota=None,
                registered=registered,
                clinic_room=room,
                is_full=is_full
            ))
            
        return slots

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def fetch_clinic_progress(self, room: str, period: str, dept_code: str = None, doctor_name: str = None, **kwargs) -> Optional[ClinicProgress]:
        if not dept_code:
            logger.warning(f"[{self.HOSPITAL_CODE}] fetch_clinic_progress needs dept_code")
            return None
            
        # API endpoints: try OutpatientProcess2 first (standard), then 3 (special sections like WBC)
        api_endpoints = ["OutpatientProcess2", "OutpatientProcess3"]
        if dept_code == "WBC":
            # For WBC, try 3 first as suggested by user
            api_endpoints = ["OutpatientProcess3", "OutpatientProcess2"]

        period_map = {"1": "上午", "2": "下午", "3": "晚上"}
        target_period = period_map.get(period, period)
        
        # We might need to try multiple dept_codes if searching in WBC as fallback
        dept_codes_to_try = [dept_code]
        # Robustness: if they specify a doctor name, and it's not found in their primary dept, 
        # we try searching in "WBC" (Well Baby Clinic) as it often contains pediatricians from various sub-depts.
        if dept_code != "WBC" and doctor_name:
            dept_codes_to_try.append("WBC")

        for try_dept in dept_codes_to_try:
            for api in api_endpoints:
                url = f"https://www.vghtc.gov.tw/APIPage/{api}"
                params = {
                    "SECTION_ID": try_dept,
                    "SECTION_NAME": "",
                    "WebMenuID": "7ee59e49-b2b8-4e1a-a3cb-45360caab01c"
                }
                
                try:
                    resp = await self.client.get(url, params=params)
                    if resp.status_code != 200:
                        continue
                        
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    table = soup.find('table')
                    if not table:
                        continue
                    
                    found_rows = []
                    for tr in table.find_all('tr'):
                        tds = tr.find_all('td')
                        if len(tds) < 8:
                            continue
                        found_rows.append(tds)

                    for tds in found_rows:
                        row_period = tds[0].text.strip()
                        row_room = tds[1].text.strip()
                        row_doctor = tds[2].text.strip()
                        
                        # Flexible period matching
                        short_p = target_period[:1]
                        if short_p not in row_period:
                            continue

                        # Doctor name matching
                        if doctor_name:
                            clean_row_doctor = row_doctor.replace(" ", "").replace("醫師", "")
                            clean_target_doctor = doctor_name.replace(" ", "").replace("醫師", "")
                            if clean_target_doctor not in clean_row_doctor:
                                continue
                        
                        # Room matching (optional match if provided)
                        if room and room.strip() and room.strip() not in row_room:
                            continue

                        total_quota_str = tds[3].text.strip()
                        current_num_str = tds[4].text.strip()
                        over_num_str = tds[5].text.strip()  # 過號看診號
                        waiting_registered_str = tds[6].text.strip()  # 已報到待看診人次
                        remark_str = tds[7].text.strip()  # td[7] = 備註/公告 (NOT status)
                        
                        current_number = None
                        if current_num_str.isdigit():
                            current_number = int(current_num_str)
                        else:
                            # Handle things like "3 (過號)"
                            match = re.search(r'\d+', current_num_str)
                            if match:
                                current_number = int(match.group())
                        
                        # Determine actual clinic status from context
                        # td[7] is a remark/notice column, not an actual status indicator
                        if '停診' in remark_str or '停診' in current_num_str:
                            actual_status = '停診'
                        elif current_number is not None and current_number > 0:
                            actual_status = '看診中'
                        elif current_num_str == '' or current_num_str == '0':
                            actual_status = '未開診'
                        else:
                            actual_status = '看診中'
                                
                        total_quota = None
                        if total_quota_str.isdigit():
                            total_quota = int(total_quota_str)
                        
                        waiting_count = None
                        if waiting_registered_str.isdigit():
                            waiting_count = int(waiting_registered_str)
                        
                        # Map to expected fields in ClinicProgress
                        return ClinicProgress(
                            clinic_room=row_room,
                            session_type=target_period,
                            current_number=current_number or 0,
                            total_quota=total_quota,
                            registered_count=total_quota, # Use total_quota as estimate
                            status=actual_status,
                            clinic_queue_details=[{"waiting_count": waiting_count}] if waiting_count is not None else []
                        )
                except Exception as e:
                    logger.error(f"[{self.HOSPITAL_CODE}] Error fetching from {api} {try_dept}: {e}")
                    
        return None

    def calculate_remaining_count(self, current_number: int, target_number: int, clinic_queue_details: list[dict]) -> int:
        return max(0, target_number - current_number)
