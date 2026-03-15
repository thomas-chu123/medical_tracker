import asyncio
import csv
import sys
import os
from datetime import datetime
from typing import List, Dict, Any, Type

# Add the project root to sys.path to import app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.scrapers.hospital_registry import HOSPITAL_SCRAPERS, get_available_hospitals
from app.scrapers.base import BaseScraper, DepartmentData, DoctorSlot, ClinicProgress
from app.core.timezone import now_tw

# Mapping for English names
HOSPITAL_EN_NAMES = {
    "CMUH_TAICHUNG": "cmuh",
    "CMUH_HSINCHU": "cmuh_hsinchu",
    "NTUH_HSINCHU": "ntuh_hsinchu",
    "HMMH": "hmmh",
    "TVGH_TAICHUNG": "tvgh_taichung",
    "TVGH_HSINCHU": "tvgh_hsinchu",
    "TYGH_HSINCHU": "tygh",
    "CGH_HSINCHU": "cgh_hsinchu",
}

async def scrape_master_data(scraper: BaseScraper, dept_code: str) -> List[DoctorSlot]:
    print(f"Scraping master data for department: {dept_code}...")
    try:
        schedule = await scraper.fetch_schedule(dept_code)
        return schedule
    except Exception as e:
        print(f"Error fetching schedule: {e}")
        return []

async def scrape_daily_progress(scraper: BaseScraper, schedule: List[DoctorSlot]) -> List[Dict[str, Any]]:
    today = now_tw().date()
    progress_data = []
    
    # Filter sessions for today
    today_sessions = [s for s in schedule if s.session_date == today]
    
    if not today_sessions:
        print("No clinic sessions found for today.")
        return []

    print(f"Found {len(today_sessions)} sessions for today. Fetching progress...")
    
    for session in today_sessions:
        if not session.clinic_room:
            continue
            
        period_map = {"上午": "1", "下午": "2", "晚上": "3"}
        period = period_map.get(session.session_type, "1")
        
        print(f"Fetching progress for {session.doctor_name} at room {session.clinic_room} ({session.session_type})...")
        try:
            progress = await scraper.fetch_clinic_progress(
                room=session.clinic_room,
                period=period,
                dept_code=session.department_code,
                doctor_no=session.doctor_no
            )
            
            if progress:
                progress_dict = {
                    "doctor_name": session.doctor_name,
                    "doctor_no": session.doctor_no,
                    "session_type": session.session_type,
                    "clinic_room": progress.clinic_room,
                    "current_number": progress.current_number,
                    "total_quota": progress.total_quota,
                    "registered_count": progress.registered_count,
                    "status": progress.status,
                }
                progress_data.append(progress_dict)
        except Exception as e:
            print(f"Error fetching progress for {session.doctor_name}: {e}")
            
    return progress_data

def save_to_csv(filename: str, data: List[Dict[str, Any]], fieldnames: List[str]):
    if not data:
        print(f"No data to save for {filename}.")
        return

    try:
        with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)
        print(f"Successfully saved to {filename}")
    except Exception as e:
        print(f"Error saving to CSV: {e}")

async def main():
    print("=== Scraper Debug Tool ===")
    
    # 1. Hospital Selection
    available = get_available_hospitals()
    print("\nSelect a hospital:")
    h_codes = sorted(available.keys())
    for i, code in enumerate(h_codes, 1):
        print(f"{i}. {code} ({available[code]})")
    
    try:
        choice = int(input("\nEnter choice (number): "))
        h_code = h_codes[choice - 1]
    except (ValueError, IndexError):
        print("Invalid choice. Exiting.")
        return

    scraper_class = HOSPITAL_SCRAPERS[h_code]
    scraper = scraper_class()
    hospital_en = HOSPITAL_EN_NAMES.get(h_code, h_code.lower())
    date_str = datetime.now().strftime("%Y%m%d")

    # 2. Department Selection
    print(f"\nFetching departments for {h_code}...")
    try:
        depts = await scraper.fetch_departments()
    except Exception as e:
        print(f"Error fetching departments: {e}")
        return

    print("\nSelect a department:")
    for i, dept in enumerate(depts, 1):
        print(f"{i}. {dept.name} ({dept.code})")
    
    try:
        choice = int(input("\nEnter choice (number): "))
        selected_dept = depts[choice - 1]
    except (ValueError, IndexError):
        print("Invalid choice. Exiting.")
        return

    # 3. Scrape Master Data
    schedule = await scrape_master_data(scraper, selected_dept.code)
    
    master_filename = f"master_{hospital_en}_{date_str}.csv"
    master_fields = ["doctor_no", "doctor_name", "department_code", "session_date", "session_type", "total_quota", "registered", "clinic_room"]
    
    # Convert dataclasses to dicts for CSV
    master_list = []
    for s in schedule:
        master_list.append({
            "doctor_no": s.doctor_no,
            "doctor_name": s.doctor_name,
            "department_code": s.department_code,
            "session_date": s.session_date,
            "session_type": s.session_type,
            "total_quota": s.total_quota,
            "registered": s.registered,
            "clinic_room": s.clinic_room
        })
    
    save_to_csv(master_filename, master_list, master_fields)

    # 4. Scrape Daily Progress
    daily_data = await scrape_daily_progress(scraper, schedule)
    
    daily_filename = f"daily_{hospital_en}_{date_str}.csv"
    daily_fields = ["doctor_name", "doctor_no", "session_type", "clinic_room", "current_number", "total_quota", "registered_count", "status"]
    
    save_to_csv(daily_filename, daily_data, daily_fields)

    print("\nDone!")

if __name__ == "__main__":
    asyncio.run(main())
