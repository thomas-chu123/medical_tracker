import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import date, datetime, time
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
    
    # Mock now_tw() to return 07:30 Taiwan time
    mock_now = datetime(2024, 1, 1, 7, 30)
    with patch("app.scheduler.now_tw") as mock_now_tw:
        mock_now_tw.return_value = mock_now
        with patch("app.scheduler.today_tw") as mock_today_tw:
            mock_today_tw.return_value = date.today()
            
            row = await _build_snapshot_row(scraper, slot, "doc_id", "dept_id", True)
            
            # Before 08:00, current_number should NOT be in the row
            assert "current_number" not in row
            assert row["current_registered"] == 40
            scraper.fetch_clinic_progress.assert_not_called()

@pytest.mark.asyncio
async def test_build_snapshot_row_morning_post_gate():
    """Test that progress IS fetched after 08:00 for morning session."""
    scraper = AsyncMock()
    scraper.fetch_clinic_progress.return_value = ClinicProgress(
        clinic_room="101", session_type="1", current_number=25,
        total_quota=60, registered_count=45, status="看診中"
    )
    
    today = date.today()
    slot = DoctorSlot(
        doctor_no="D1", doctor_name="Doc1", department_code="01",
        session_date=today, session_type="上午",
        total_quota=50, registered=40, clinic_room="101", current_number=None
    )
    
    # Mock now_tw() to return 09:00 Taiwan time on today's date
    mock_now = datetime.combine(today, time(9, 0))
    with patch("app.scheduler.now_tw") as mock_now_tw:
        mock_now_tw.return_value = mock_now
        with patch("app.scheduler.today_tw") as mock_today_tw:
            mock_today_tw.return_value = today
            
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
    
    # Mock today_tw() to return today so that future_date will not match
    with patch("app.scheduler.today_tw") as mock_today_tw:
        mock_today_tw.return_value = date.today()
        
        row = await _build_snapshot_row(scraper, slot, "doc_id", "dept_id", True)
        # For future dates, we still return a row but without current_number
        # (we skip real-time progress fetch for non-today sessions)
        assert row is not None
        assert "current_number" not in row
        assert row["current_registered"] == 40
        scraper.fetch_clinic_progress.assert_not_called()

@pytest.mark.asyncio
async def test_build_snapshot_row_afternoon_gate():
    """Test afternoon session gate (13:30)."""
    scraper = AsyncMock()
    scraper.fetch_clinic_progress.return_value = ClinicProgress(
        clinic_room="101", session_type="2", current_number=10
    )
    
    today = date.today()
    slot = DoctorSlot(
        doctor_no="D1", doctor_name="Doc1", department_code="01",
        session_date=today, session_type="下午",
        total_quota=50, registered=40, clinic_room="101", current_number=None
    )
    
    # 12:30 -> No fetch
    with patch("app.scheduler.now_tw") as mock_now_tw:
        with patch("app.scheduler.today_tw") as mock_today_tw:
            mock_now_tw.return_value = datetime.combine(today, time(12, 30))
            mock_today_tw.return_value = today
            row = await _build_snapshot_row(scraper, slot, "doc_id", "dept_id", True)
            # Before 13:30, current_number should NOT be in the row
            assert "current_number" not in row
            assert row["current_registered"] == 40
        
    # 13:30 -> Fetch
    with patch("app.scheduler.now_tw") as mock_now_tw:
        with patch("app.scheduler.today_tw") as mock_today_tw:
            mock_now_tw.return_value = datetime.combine(today, time(13, 30))
            mock_today_tw.return_value = today
            row = await _build_snapshot_row(scraper, slot, "doc_id", "dept_id", True)
            assert row["current_number"] == 10
