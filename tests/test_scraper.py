"""Tests for the CMUH scraper."""
import asyncio
import pytest
import allure
import re
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
@allure.story("Regex: Clinic Progress Parsing from reg64 HTML")
def test_reg64_clinic_progress_regex():
    """Test the clinic progress regex pattern used in `fetch_clinic_progress`."""
    # Test finding status "看診完畢"
    html_finished = '<td class="table-info" style="color:red">看診完畢</td>'
    assert "看診完畢" in html_finished
    
    # Test current number extraction
    html_number = '<div style="text-align:center;">診間燈號：37</div>'
    match = re.search(r"診間燈號[：:]\s*(\d+)", html_number)
    assert match and int(match.group(1)) == 37
