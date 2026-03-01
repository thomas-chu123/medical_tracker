"""
Tests for the NTUH Hsinchu scraper.

這個測試套件涵蓋 NTUHHsinchuScraper 的核心功能：
- fetch_departments(): 從 RegShowBlock API 提取科室列表
- fetch_schedule(dept_code): 從科室代碼提取醫師排程
- fetch_clinic_progress(room, period): 從 ClinicCurrentLightNo API 提取即時進度

測試策略：
- 單元測試：測試與模擬數據的邏輯
- 整合測試：測試與真實 API 的交互
- 端到端測試：驗證排程器和資料庫整合
"""

import asyncio
import pytest
import allure
from datetime import date
from app.scrapers.ntuh import NTUHHsinchuScraper, DepartmentData, DoctorSlot, ClinicProgress
import tenacity


# ─────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────

@pytest.fixture
def scraper():
    """Create a fresh scraper instance for testing."""
    s = NTUHHsinchuScraper()
    yield s
    # We can't automatically await s.close() in sync fixture, handled in tests


# ─────────────────────────────────────────────────────────
# Unit Tests: fetch_departments()
# ─────────────────────────────────────────────────────────

@allure.feature("Scraper-NTUH")
@allure.story("Fetch Departments")
@pytest.mark.asyncio
async def test_ntuh_fetch_departments_returns_valid_structure():
    """
    單元測試：驗證 fetch_departments() 回傳正確的資料結構。
    
    檢查項目：
    - 回傳類型為 list[DepartmentData]
    - 每個 DepartmentData 有必要欄位：name, code, hospital_code
    - hospital_code 為 "NTUH_HSINCHU"
    """
    scraper = NTUHHsinchuScraper()
    try:
        departments = await scraper.fetch_departments()
        
        # Verify return type
        assert isinstance(departments, list), "Should return a list"
        
        # If departments exist, verify structure
        if departments:
            for dept in departments:
                assert isinstance(dept, DepartmentData), "Should return DepartmentData instances"
                assert dept.code, f"Department code should not be empty for {dept.name}"
                assert dept.name, "Department name should not be empty"
                assert dept.hospital_code == "NTUH_HSINCHU", "Hospital code should be NTUH_HSINCHU"
    finally:
        await scraper.close()


@allure.feature("Scraper-NTUH")
@allure.story("Fetch Departments")
@pytest.mark.asyncio
async def test_ntuh_fetch_departments_live_site():
    """
    整合測試：從 NTUH 真實網站提取科室列表。
    
    這是一個實時測試，需要網絡連接。
    """
    scraper = NTUHHsinchuScraper()
    try:
        try:
            departments = await scraper.fetch_departments()
            
            # NTUH Hsinchu should have multiple departments
            assert len(departments) >= 10, "Should find at least 10 departments"
            
            # Verify some known departments exist
            dept_codes = {d.code for d in departments}
            
            # Check for some common departments
            expected_codes = {"MED", "SURG", "ORTH", "PED"}  # 內科、外科、骨科、小兒
            found_codes = expected_codes & dept_codes
            assert len(found_codes) > 0, f"Should find some expected departments. Found: {dept_codes}"
        except tenacity.RetryError as e:
            pytest.skip(f"Live site connection failed: {e}")
    finally:
        await scraper.close()


# ─────────────────────────────────────────────────────────
# Unit Tests: fetch_schedule()
# ─────────────────────────────────────────────────────────

@allure.feature("Scraper-NTUH")
@allure.story("Fetch Schedule")
@pytest.mark.asyncio
async def test_ntuh_fetch_schedule_period_encoding():
    """
    單元測試：驗證 fetch_schedule() 的時段編碼正確。
    
    檢查項目：
    - 回傳類型為 list[DoctorSlot]
    - 每個 DoctorSlot 的 session_type 在 ["上午", "下午", "晚上"] 中
    - 必要欄位：doctor_name, doctor_no, department_code, session_date, session_type
    """
    scraper = NTUHHsinchuScraper()
    try:
        # Test with a known department code
        slots = await scraper.fetch_schedule("MED")
        
        # Verify return type
        assert isinstance(slots, list), "Should return a list"
        
        # Verify structure if slots exist
        if slots:
            valid_session_types = {"上午", "下午", "晚上"}
            for slot in slots:
                assert isinstance(slot, DoctorSlot), "Should return DoctorSlot instances"
                assert slot.doctor_name, "Doctor name should not be empty"
                assert slot.doctor_no, "Doctor number should not be empty"
                assert slot.department_code == "MED", "Department code should match"
                assert slot.session_type in valid_session_types, \
                    f"Session type should be one of {valid_session_types}, got {slot.session_type}"
                assert isinstance(slot.session_date, date), "Session date should be a date object"
    finally:
        await scraper.close()


@allure.feature("Scraper-NTUH")
@allure.story("Fetch Schedule")
@pytest.mark.asyncio
async def test_ntuh_fetch_schedule_live_site():
    """
    整合測試：從 NTUH 真實網站提取特定科室的醫師排程。
    """
    scraper = NTUHHsinchuScraper()
    try:
        try:
            # Fetch schedule for internal medicine department
            slots = await scraper.fetch_schedule("MED")
            
            # NTUH MED department should have doctors
            assert isinstance(slots, list), "Should return a list"
            # May be empty if no doctors available at this moment, so we don't assert length
            
            if slots:
                # Verify period coding
                valid_periods = {"上午", "下午", "晚上"}
                for slot in slots:
                    assert slot.session_type in valid_periods, \
                        f"Invalid session type: {slot.session_type}"
        except tenacity.RetryError as e:
            pytest.skip(f"Live site connection failed: {e}")
    finally:
        await scraper.close()


# ─────────────────────────────────────────────────────────
# Unit Tests: fetch_clinic_progress()
# ─────────────────────────────────────────────────────────

@allure.feature("Scraper-NTUH")
@allure.story("Fetch Clinic Progress")
@pytest.mark.asyncio
async def test_ntuh_fetch_clinic_progress_optional_fields():
    """
    單元測試：驗證 fetch_clinic_progress() 正確回傳 Optional[ClinicProgress]。
    
    檢查項目：
    - 回傳 None 或 ClinicProgress
    - 若回傳 ClinicProgress，必要欄位：clinic_room, session_type, current_number
    - current_number 應該是整數
    """
    scraper = NTUHHsinchuScraper()
    try:
        # Test with valid room and period
        progress = await scraper.fetch_clinic_progress("1", "1")
        
        # Can be None or ClinicProgress
        assert progress is None or isinstance(progress, ClinicProgress), \
            "Should return None or ClinicProgress"
        
        if progress:
            # Verify structure
            assert isinstance(progress.clinic_room, str), "Clinic room should be string"
            assert progress.session_type in {"上午", "下午", "晚上"}, \
                "Session type should be valid"
            assert isinstance(progress.current_number, int), \
                "Current number should be integer"
    finally:
        await scraper.close()


@allure.feature("Scraper-NTUH")
@allure.story("Fetch Clinic Progress")
@pytest.mark.asyncio
async def test_ntuh_clinic_progress_numeric_parsing():
    """
    單元測試：驗證診療進度的數值解析。
    
    檢查項目：
    - current_number、total_quota、registered_count 應解析為整數，不是字符串
    """
    scraper = NTUHHsinchuScraper()
    try:
        # Try different room/period combinations
        test_cases = [
            ("1", "1"),  # Room 1, Morning
            ("5", "2"),  # Room 5, Afternoon
            ("10", "3"), # Room 10, Evening
        ]
        
        for room, period in test_cases:
            progress = await scraper.fetch_clinic_progress(room, period)
            
            if progress:
                # Verify numeric types
                assert isinstance(progress.current_number, int), \
                    f"current_number for room {room} should be int, got {type(progress.current_number)}"
                
                if progress.total_quota is not None:
                    assert isinstance(progress.total_quota, int), \
                        f"total_quota should be int or None, got {type(progress.total_quota)}"
                
                if progress.registered_count is not None:
                    assert isinstance(progress.registered_count, int), \
                        f"registered_count should be int or None, got {type(progress.registered_count)}"
    finally:
        await scraper.close()


@allure.feature("Scraper-NTUH")
@allure.story("Fetch Clinic Progress")
@pytest.mark.asyncio
async def test_ntuh_clinic_progress_live_site():
    """
    整合測試：從 NTUH 真實網站查詢即時看診進度。
    """
    scraper = NTUHHsinchuScraper()
    try:
        try:
            # Query current clinic progress
            progress = await scraper.fetch_clinic_progress("1", "1")
            
            # May be None if no progress data available
            if progress:
                assert isinstance(progress.current_number, int), \
                    "Current number should be integer"
                assert progress.session_type in {"上午", "下午", "晚上"}, \
                    "Session type should be valid"
        except tenacity.RetryError as e:
            pytest.skip(f"Live site connection failed: {e}")
    finally:
        await scraper.close()


# ─────────────────────────────────────────────────────────
# Integration Tests: Scheduler Context
# ─────────────────────────────────────────────────────────

@allure.feature("Scraper-NTUH")
@allure.story("Scheduler Integration")
@pytest.mark.asyncio
async def test_ntuh_hsinchu_scraper_in_scheduler_context():
    """
    整合測試：驗證爬蟲在排程器上下文中執行無誤。
    
    這個測試驗證爬蟲是否能夠：
    1. 在 get_enabled_scrapers() 中被正確加載
    2. 執行三個核心方法而不出錯
    """
    from app.scrapers.hospital_registry import get_enabled_scrapers
    
    # Get all enabled scrapers
    scrapers = get_enabled_scrapers()
    
    # Find NTUH scraper
    ntuh_scraper = None
    for scraper in scrapers:
        if scraper.HOSPITAL_CODE == "NTUH_HSINCHU":
            ntuh_scraper = scraper
            break
    
    # NTUH may not be enabled in test environment
    if ntuh_scraper:
        try:
            # Test basic operation
            departments = await ntuh_scraper.fetch_departments()
            assert isinstance(departments, list), "Should return departments list"
        finally:
            await ntuh_scraper.close()
    else:
        # If not enabled, that's okay for this test
        pytest.skip("NTUH_HSINCHU not enabled in test environment")


# ─────────────────────────────────────────────────────────
# Utility Tests
# ─────────────────────────────────────────────────────────

@allure.feature("Scraper-NTUH")
@allure.story("Utility Functions")
def test_parse_int_utility():
    """Test the _parse_int utility function."""
    from app.scrapers.ntuh import _parse_int
    
    # Valid cases
    assert _parse_int("100") == 100
    assert _parse_int("已掛號：50") == 50
    assert _parse_int("  42  ") == 42
    
    # Edge cases
    assert _parse_int(None) is None
    assert _parse_int("") is None
    assert _parse_int("No numbers") is None


@allure.feature("Scraper-NTUH")
@allure.story("Client Management")
@pytest.mark.asyncio
async def test_scraper_client_lifecycle():
    """Test that the scraper client is properly initialized and closed."""
    scraper = NTUHHsinchuScraper()
    
    # Initially, no client should exist
    assert scraper._client is None, "Client should not exist initially"
    
    # Get client
    client = await scraper._get_client()
    assert client is not None, "Should return a client"
    
    # Get client again should return same instance
    client2 = await scraper._get_client()
    assert client is client2, "Should return the same client instance"
    
    # Close
    await scraper.close()
    assert scraper._client.is_closed, "Client should be closed"
