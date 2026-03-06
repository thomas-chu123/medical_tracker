"""
Test script for TYGH_HSINCHU scraper

Usage:
    python -m pytest tests/scraper/test_tygh_hsinchu_scraper.py -xvs
"""

import asyncio
from datetime import date
import pytest
from unittest.mock import AsyncMock, patch
from bs4 import BeautifulSoup
from app.scrapers.tygh_hsinchu import TyghHsinchuScraper

MOCK_TYGH_DEPT_HTML = """
<!DOCTYPE html>
<html>
<body>
<div class="test">
    <a href="WebRegList_Dept.aspx?d=07">腸胃肝膽內科</a>
    <a href="WebRegList_Dept.aspx?d=11">一般外科</a>
</div>
</body>
</html>
"""

MOCK_TYGH_DEPT_SCHED_HTML = """
<!DOCTYPE html>
<html>
<body>
    <a href='WebRegList_Doct.aspx?dn=0709&d=07' class='bb'>鄧堯州</a>
</body>
</html>
"""

MOCK_TYGH_SCHEDULE_HTML = """
<!DOCTYPE html>
<html>
<body>
    <span id="ctl00_ContentPlaceHolder1_LabDoct">
        <table class="today-table">
            <tr>
                <td class="table-day">
                    <div>
                        <input id='c0' type='radio' name='RadioDoct' value='0A1150309A1A07A1'>
                        <font color='000000'><label for='c0'>115/03/09</br>已掛號:38人</label></font>
                    </div>
                </td>
                <td class="table-day">
                    <div>
                        <input id='c1' type='radio' name='RadioDoct' value='1A1150406A1A07A1'>
                        <font color='FF0000'><label for='c1'>115/04/06</br>停診</label></font>
                    </div>
                </td>
            </tr>
        </table>
    </span>
</body>
</html>
"""

MOCK_TYGH_PROGRESS_HTML = """
<!DOCTYPE html>
<html>
<body>
    <table>
        <tr>
            <td>腸胃肝膽內科</td>
            <td>鄧堯州</td>
            <td>52</td>
        </tr>
    </table>
</body>
</html>
"""

@pytest.mark.asyncio
async def test_fetch_departments():
    scraper = TyghHsinchuScraper()
    async def mock_get(url, **kwargs):
        return MOCK_TYGH_DEPT_HTML
    
    try:
        with patch.object(scraper, '_get', side_effect=mock_get):
            depts = await scraper.fetch_departments()
            assert len(depts) == 2
            assert depts[0].code == "07"
            assert depts[0].name == "腸胃肝膽內科"
            assert depts[0].category == "內科系"
            
            assert depts[1].code == "11"
            assert depts[1].category == "外科系"
    finally:
        await scraper.close()

@pytest.mark.asyncio
async def test_fetch_schedule():
    scraper = TyghHsinchuScraper()
    
    async def mock_get(url, **kwargs):
        if "WebRegList_Dept" in url:
            return MOCK_TYGH_DEPT_SCHED_HTML
        if "WebRegList_Doct" in url:
            return MOCK_TYGH_SCHEDULE_HTML
        return ""
    
    try:
        with patch.object(scraper, '_get', side_effect=mock_get):
            slots = await scraper.fetch_schedule("07")
            assert len(slots) == 2
            
            slot1 = slots[0]
            assert slot1.doctor_name == "鄧堯州"
            assert slot1.doctor_no == "0709"
            assert slot1.session_date == date(2026, 3, 9)
            assert slot1.session_type == "上午"
            assert slot1.is_full is False
            assert slot1.status is None

            slot2 = slots[1]
            assert slot2.session_date == date(2026, 4, 6)
            assert slot2.is_full is True
            assert slot2.status == "休診"
    finally:
        await scraper.close()

@pytest.mark.asyncio
async def test_fetch_clinic_progress():
    scraper = TyghHsinchuScraper()
    async def mock_get(url, **kwargs):
        return MOCK_TYGH_PROGRESS_HTML
    
    try:
        with patch.object(scraper, '_get', side_effect=mock_get):
            progress = await scraper.fetch_clinic_progress("07", "1", dept_name="腸胃肝膽內科")
            assert progress is not None
            assert progress.current_number == 52
            assert progress.clinic_queue_details[0]["doctor"] == "鄧堯州"
            assert progress.session_type == "上午"

            # Test not found case
            progress2 = await scraper.fetch_clinic_progress("22", "1", dept_name="家庭醫學科")
            assert progress2 is None
    finally:
        await scraper.close()

def test_calculate_remaining_count():
    scraper = TyghHsinchuScraper()
    assert scraper.calculate_remaining_count(52, 60, []) == 8
    assert scraper.calculate_remaining_count(60, 52, []) == 0
