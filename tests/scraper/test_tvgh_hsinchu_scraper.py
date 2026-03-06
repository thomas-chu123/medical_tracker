"""
Test script for TVGH_HSINCHU scraper

Usage:
    python -m pytest tests/scraper/test_tvgh_hsinchu_scraper.py -xvs
"""

import asyncio
from datetime import date
import pytest
from unittest.mock import AsyncMock, patch
from bs4 import BeautifulSoup
from app.scrapers.tvgh_hsinchu import TvghHsinchuScraper

MOCK_TVGH_DEPT_HTML = """
<!DOCTYPE html>
<html>
<body>
<table width="85%" style="margin:0 auto;">
    <tr><th colspan="5" >內科系門診</th></tr>
    <tr>
        <td width="20%" >
            <a href ="listDoctor.jsp?init=init&section=CM">胸腔內科</a>
        </td>
    </tr>
</table>
</body>
</html>
"""

MOCK_TVGH_SCHEDULE_HTML = """
<!DOCTYPE html>
<html>
<body>
<table>
    <tr>
        <td>
            <form name="T20260403A0207" action="initPrompt.jsp" method="post">
                <input type="hidden" name="sectionChineseName" value="胸腔內科">
                <input type="hidden" name="consultRoomLocation" value="第18診">
                <input type="hidden" name="doctorChineseName" value="邱華彥醫師">
                <input type="hidden" name="consultDateAD" value="20260403">
                <input type="hidden" name="consultNoonFlag" value="A">
                <input type="hidden" name="doctorNumber" value="0530A">
            </form>
        </td>
        <td>
            <form name="T20260403P0207" action="initPrompt.jsp" method="post">
                <input type="hidden" name="sectionChineseName" value="胸腔內科">
                <input type="hidden" name="consultRoomLocation" value="第18診">
                <input type="hidden" name="doctorChineseName" value="邱華彥醫師">
                <input type="hidden" name="consultDateAD" value="20260403">
                <input type="hidden" name="consultNoonFlag" value="P">
                <input type="hidden" name="doctorNumber" value="0530A">
            </form>
        </td>
    </tr>
</table>
</body>
</html>
"""

MOCK_TVGH_PROGRESS_HTML = """
<!DOCTYPE html>
<html>
<body>
    <div class="flip"><span class="1">上午診</span></div>
    <div class="panel">
        <div class="grid-item">
            <table>
            <tr><td class="td1">邱華彥<br/>胸腔內科</td></tr>
            <tr><td class="td2">52</td></tr>
            </table>
        </div>
    </div>
</body>
</html>
"""

@pytest.mark.asyncio
async def test_fetch_departments():
    scraper = TvghHsinchuScraper()
    async def mock_get(url, **kwargs):
        return MOCK_TVGH_DEPT_HTML
    
    try:
        with patch.object(scraper, '_get', side_effect=mock_get):
            depts = await scraper.fetch_departments()
            assert len(depts) == 1
            assert depts[0].code == "CM"
            assert depts[0].name == "胸腔內科"
            assert depts[0].category == "內科系"
    finally:
        await scraper.close()

@pytest.mark.asyncio
async def test_fetch_schedule():
    scraper = TvghHsinchuScraper()
    async def mock_get(url, **kwargs):
        return MOCK_TVGH_SCHEDULE_HTML
    
    try:
        with patch.object(scraper, '_get', side_effect=mock_get):
            slots = await scraper.fetch_schedule("CM")
            assert len(slots) == 2
            
            slot1 = slots[0]
            assert slot1.doctor_name == "邱華彥"
            assert slot1.doctor_no == "0530A"
            assert slot1.session_date == date(2026, 4, 3)
            assert slot1.session_type == "上午"
            assert slot1.clinic_room == "第18診"

            slot2 = slots[1]
            assert slot2.session_type == "下午"
    finally:
        await scraper.close()

@pytest.mark.asyncio
async def test_fetch_clinic_progress():
    scraper = TvghHsinchuScraper()
    async def mock_get(url, **kwargs):
        return MOCK_TVGH_PROGRESS_HTML
    
    try:
        with patch.object(scraper, '_get', side_effect=mock_get):
            progress = await scraper.fetch_clinic_progress("胸腔內科", "1")
            assert progress is not None
            assert progress.current_number == 52
            assert progress.clinic_queue_details[0]["doctor"] == "邱華彥"

            # Test period not found case 
            progress2 = await scraper.fetch_clinic_progress("胸腔內科", "unknown")
            assert progress2 is None
    finally:
        await scraper.close()

def test_calculate_remaining_count():
    scraper = TvghHsinchuScraper()
    assert scraper.calculate_remaining_count(52, 60, []) == 8
    assert scraper.calculate_remaining_count(60, 52, []) == 0
