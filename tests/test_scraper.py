"""Tests for the CMUH scraper."""
import asyncio
import pytest
from app.scrapers.cmuh import CMUHScraper


@pytest.mark.asyncio
async def test_fetch_departments():
    """Integration test: fetch departments from CMUH live website."""
    scraper = CMUHScraper()
    try:
        departments = await scraper.fetch_departments()
        assert len(departments) > 0, "Should find at least one department"
        for dept in departments:
            assert dept.code, "Department code should not be empty"
            assert dept.name, "Department name should not be empty"
        print(f"✅ Found {len(departments)} departments")
    finally:
        await scraper.close()


@pytest.mark.asyncio
async def test_parse_date():
    from app.scrapers.cmuh import CMUHScraper
    from datetime import date

    scraper = CMUHScraper()
    # AD year
    assert scraper._parse_date("2024/03/15") == date(2024, 3, 15)
    # ROC year
    assert scraper._parse_date("113/03/15") == date(2024, 3, 15)
    # With surrounding text
    assert scraper._parse_date("日期：2024-03-15（五）") == date(2024, 3, 15)
    # Invalid
    assert scraper._parse_date("N/A") is None
    await scraper.close()


@pytest.mark.asyncio
async def test_normalize_session_type():
    from app.scrapers.cmuh import CMUHScraper
    scraper = CMUHScraper()
    assert scraper._normalize_session_type("上午診") == "上午"
    assert scraper._normalize_session_type("下午門診") == "下午"
    assert scraper._normalize_session_type("晚上") == "晚上"
    assert scraper._normalize_session_type("AM") == "上午"
    await scraper.close()
