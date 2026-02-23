import pytest
from unittest.mock import MagicMock, AsyncMock
from datetime import date
from app.scrapers.base import DoctorSlot, ClinicProgress

@pytest.fixture
def mock_supabase():
    mock = MagicMock()
    # Mock some common chains
    mock.table.return_value.select.return_value.execute.return_value.data = []
    mock.table.return_value.insert.return_value.execute.return_value.data = []
    return mock

@pytest.fixture
def mock_settings():
    from app.config import Settings
    return Settings(
        supabase_url="https://test.supabase.co",
        supabase_key="test-key",
        line_notify_client_id="id",
        line_notify_client_secret="secret",
        smtp_server="localhost",
        smtp_port=1025,
        smtp_user="test@example.com",
        smtp_password="password",
        admin_email="admin@example.com"
    )

@pytest.fixture
def sample_doctor_slot():
    return DoctorSlot(
        doctor_no="D6351",
        doctor_name="孟志瀚",
        department_code="0600",
        session_date=date.today(),
        session_type="上午",
        total_quota=50,
        registered=45,
        clinic_room="230"
    )

@pytest.fixture
def sample_clinic_progress():
    return ClinicProgress(
        clinic_room="230",
        session_type="上午",
        current_number=37,
        total_quota=50,
        registered_count=48,
        status="看診中"
    )
