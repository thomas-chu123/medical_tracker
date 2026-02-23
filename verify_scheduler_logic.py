import asyncio
from datetime import date, datetime
import sys
import os

# Add project root to sys.path
sys.path.append(os.getcwd())

from app.scheduler import _build_snapshot_row
from app.scrapers.base import DoctorSlot, ClinicProgress

class MockScraper:
    HOSPITAL_CODE = "TEST"
    async def fetch_clinic_progress(self, room, period):
        # Standardized: registered_count = Headcount (人數), total_quota = Max Number (總號)
        return ClinicProgress(
            clinic_room=room,
            session_type="1",
            current_number=15,
            total_quota=50,      # Max Number
            registered_count=30,  # Headcount
            status="看診中"
        )
    async def close(self): pass

async def test_build_snapshot_row():
    scraper = MockScraper()
    today = date.today()
    slot = DoctorSlot(
        doctor_no="D123",
        doctor_name="Test Doc",
        department_code="DEP",
        session_date=today,
        session_type="上午",
        total_quota=100, # Snapshot quota
        registered=80,    # Snapshot registered
        clinic_room="101"
    )
    
    # Mock current hour to 9 (after 8:00 morning gate)
    # We can't easily mock datetime.now() without freezegun, 
    # but we can observe our logic's dependence on it.
    
    print("Testing _build_snapshot_row for today...")
    row = await _build_snapshot_row(scraper, slot, "doc_id", "dept_id", True)
    
    now = datetime.now()
    if now.hour >= 8:
        print(f"Current hour is {now.hour}, should have fetched progress.")
        assert row["current_number"] == 15
        assert row["total_quota"] == 50
        assert row["current_registered"] == 30
    else:
        print(f"Current hour is {now.hour}, should NOT have fetched progress.")
        assert row["current_number"] is None
        assert row["total_quota"] == 100
        assert row["current_registered"] == 80
    
    print("Testing _build_snapshot_row for future date...")
    future_slot = DoctorSlot(
        doctor_no="D123",
        doctor_name="Test Doc",
        department_code="DEP",
        session_date=date(2099, 1, 1),
        session_type="上午",
        total_quota=100,
        registered=80,
        clinic_room="101"
    )
    row_future = await _build_snapshot_row(scraper, future_slot, "doc_id", "dept_id", True)
    assert row_future is None, "Future dates should be skipped in targeted scrape"
    print("Future date correctly skipped.")

    print("\nVerification Passed!")

if __name__ == "__main__":
    asyncio.run(test_build_snapshot_row())
