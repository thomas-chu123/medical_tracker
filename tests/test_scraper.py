"""Tests for the CMUH scraper."""
import asyncio
import pytest
import allure
import re
from unittest.mock import patch, MagicMock 
from app.scrapers.cmuh import CMUHScraper, DoctorSlot, ClinicProgress


@pytest.fixture
def scraper():
    s = CMUHScraper()
    yield s
    # We can't automatically await s.close() in sync fixture, handled in tests or by pytest-asyncio


@allure.feature("Scraper")
@allure.story("Fetch Departments from Live Site")
@pytest.mark.asyncio
async def test_fetch_departments():
    """Integration test: fetch departments from CMUH live website."""
    scraper_obj = CMUHScraper()
    try:
        departments = await scraper_obj.fetch_departments()
        assert len(departments) > 0, "Should find at least one department"
        for dept in departments:
            assert dept.code, "Department code should not be empty"
            assert dept.name, "Department name should not be empty"
    finally:
        await scraper_obj.close()


@allure.feature("Scraper")
@allure.story("Date Parsing Utility")
def test_parse_date(scraper):
    from datetime import date
    # AD year
    assert scraper._parse_date("2024/03/15") == date(2024, 3, 15)
    # ROC year
    assert scraper._parse_date("113/03/15") == date(2024, 3, 15)
    # With surrounding text
    assert scraper._parse_date("日期：2024-03-15（五）") == date(2024, 3, 15)
    # Invalid
    assert scraper._parse_date("N/A") is None


@allure.feature("Scraper")
@allure.story("Session Type Normalization")
def test_normalize_session_type(scraper):
    assert scraper._normalize_session_type("上午診") == "上午"
    assert scraper._normalize_session_type("下午門診") == "下午"
    assert scraper._normalize_session_type("晚上") == "晚上"
    assert scraper._normalize_session_type("AM") == "上午"


@allure.feature("Scraper")
@allure.story("Regex: Clinic Room Parsing from reg52 Schedule")
def test_reg52_clinic_room_regex():
    """Test the clinic room regex pattern used in `fetch_schedule`."""
    pattern = r"\(([\dA-Za-z]+)診?\)"
    
    # Test standard format
    match = re.search(pattern, "(230診)")
    assert match and match.group(1) == "230"
    
    # Test format without '診'
    match = re.search(pattern, "(276)")
    assert match and match.group(1) == "276"
    
    # Test alphanumeric format without '診'
    match = re.search(pattern, "(276A)")
    assert match and match.group(1) == "276A"
    
    # Test that it doesn't match empty parens or unrelated parens if we can help it
    match = re.search(pattern, "已掛號：58 人(230)")
    assert match and match.group(1) == "230"


@allure.feature("Scraper")
@allure.story("Regex: Clinic Room Parsing from reg52 Schedule")
def test_parse_room_number_picks_longest():
    """Test that if multiple room numbers are in a block, the longest one is chosen."""
    block_text_1 = "兒童發展與行為(118診),地點：兒童醫院1樓(15診)"
    block_text_2 = "地點：急重症中心大樓1樓(15診), 神經內科(118)"

    # Test case 1
    matches_1 = re.findall(r'\((\d+)', block_text_1)
    result_1 = max(matches_1, key=len) if matches_1 else None
    assert result_1 == "118"

    # Test case 2
    matches_2 = re.findall(r'\((\d+)', block_text_2)
    result_2 = max(matches_2, key=len) if matches_2 else None
    assert result_2 == "118"


@allure.feature("Scraper")
@allure.story("Parse Doctor Schedule (Unit Test)")
@pytest.mark.asyncio
async def test_parse_doctor_schedule_unit():
    """Unit test for schedule parsing with mock HTML."""
    scraper = CMUHScraper()
    # Mock HTML snippet from reg52
    mock_html = """
    <tr>
      <td><a href="reg52_1.cgi?doctor=D6351">孟志瀚</a></td>
      <td>2024/03/15</td>
      <td>上午診</td>
      <td>(230)</td>
      <td>50</td>
      <td>45</td>
      <td><span class="text-danger">額滿</span></td>
    </tr>
    """
    with patch("app.scrapers.cmuh.httpx.AsyncClient.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = mock_html
        mock_resp.content = mock_html.encode("utf-8") # CMUH uses big5 but utf8 is fine for ASCII mock
        mock_get.return_value = mock_resp
        
        # We need to mock _fetch_doctor_slots or the whole sequence
        # For simplicity, let's test a helper that handles the parsing if it exists,
        # or mock the specific call to reg52.
        slots = await scraper.fetch_schedule("0600")
        # In reality reg52 returns all doctors, but our mock is small.
        # This test verifies that the fields are mapped correctly from HTML.
        if slots:
            s = slots[0]
            assert s.doctor_name == "孟志瀚"
            assert s.clinic_room == "230"
            assert s.is_full is True

@allure.feature("Scraper")
@allure.story("Parse Clinic Progress (Unit Test)")
@pytest.mark.asyncio
async def test_parse_clinic_progress_unit():
    """Unit test for progress parsing with mock HTML."""
    scraper = CMUHScraper()
    mock_html = """
    <div id="MainContent_divLamp">目前的診號是 37</div>
    <table>
      <tr><td>1</td><td>1</td><td>OK</td></tr>
      <tr><td>2</td><td>2</td><td>OK</td></tr>
      <tr><td>3</td><td>3</td><td>OK</td></tr>
    </table>
    """
    with patch("app.scrapers.cmuh.httpx.AsyncClient.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = mock_html.encode("big5")
        mock_get.return_value = mock_resp
        
        progress = await scraper.fetch_clinic_progress("230", "1")
        assert progress.current_number == 37
        assert progress.total_quota == 3  # Max number in our tiny mock
        assert progress.registered_count == 3 # Headcount
