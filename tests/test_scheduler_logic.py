import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import date, datetime
from app.scheduler import _build_snapshot_row
from app.scrapers.base import DoctorSlot, ClinicProgress

@pytest.mark.asyncio
async def test_build_snapshot_row_morning_pre_gate():
    """Test that progress is NOT fetched before 08:00 for morning session."""
    scraper = AsyncMock()
    slot = DoctorSlot(
        doctor_no="D1", doctor_name="Doc1", department_code="01",
        session_date=date.today(), session_type="上午",
        total_quota=50, registered=40, clinic_room="101"
    )
    
    # Mocking now() to 07:30
    mock_now = datetime(2024, 1, 1, 7, 30)
    with patch("app.scheduler.datetime") as mock_datetime:
        mock_datetime.now.return_value = mock_now
        mock_datetime.combine = datetime.combine
        
        row = await _build_snapshot_row(scraper, slot, "doc_id", "dept_id", True)
        
        assert row["current_number"] is None
        scraper.fetch_clinic_progress.assert_not_called()

@pytest.mark.asyncio
async def test_build_snapshot_row_morning_post_gate():
    """Test that progress IS fetched after 08:00 for morning session."""
    scraper = AsyncMock()
    scraper.fetch_clinic_progress.return_value = ClinicProgress(
        clinic_room="101", session_type="1", current_number=25,
        total_quota=60, registered_count=45, status="看診中"
    )
    
    slot = DoctorSlot(
        doctor_no="D1", doctor_name="Doc1", department_code="01",
        session_date=date.today(), session_type="上午",
        total_quota=50, registered=40, clinic_room="101"
    )
    
    # Mocking now() to 09:00
    mock_now = datetime(2024, 1, 1, 9, 0)
    with patch("app.scheduler.datetime") as mock_datetime:
        mock_datetime.now.return_value = mock_now
        mock_datetime.combine = datetime.combine
        
        row = await _build_snapshot_row(scraper, slot, "doc_id", "dept_id", True)
        
        assert row["current_number"] == 25
        assert row["total_quota"] == 60
        assert row["current_registered"] == 45
        scraper.fetch_clinic_progress.assert_called_once_with("101", "1")

@pytest.mark.asyncio
async def test_build_snapshot_row_future_date():
    """Test that progress is NOT fetched for future dates."""
    scraper = AsyncMock()
    future_date = date(2099, 1, 1)
    slot = DoctorSlot(
        doctor_no="D1", doctor_name="Doc1", department_code="01",
        session_date=future_date, session_type="上午",
        total_quota=50, registered=40, clinic_room="101"
    )
    
    row = await _build_snapshot_row(scraper, slot, "doc_id", "dept_id", True)
    assert row is None  # We skip future dates in targeted scrape as per logic

@pytest.mark.asyncio
async def test_build_snapshot_row_afternoon_gate():
    """Test afternoon session gate (13:00)."""
    scraper = AsyncMock()
    scraper.fetch_clinic_progress.return_value = ClinicProgress(
        clinic_room="101", session_type="2", current_number=10
    )
    
    slot = DoctorSlot(
        doctor_no="D1", doctor_name="Doc1", department_code="01",
        session_date=date.today(), session_type="下午",
        total_quota=50, registered=40, clinic_room="101"
    )
    
    # 12:30 -> No fetch
    with patch("app.scheduler.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2024, 1, 1, 12, 30)
        row = await _build_snapshot_row(scraper, slot, "doc_id", "dept_id", True)
        assert row["current_number"] is None
        
    # 13:30 -> Fetch
    with patch("app.scheduler.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2024, 1, 1, 13, 30)
        row = await _build_snapshot_row(scraper, slot, "doc_id", "dept_id", True)
        assert row["current_number"] == 10
