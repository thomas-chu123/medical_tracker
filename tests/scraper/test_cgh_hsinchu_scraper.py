"""
Test script for CGHHsinchuScraper
"""

import asyncio
from datetime import date
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from app.scrapers.cgh_hsinchu import CGHHsinchuScraper

MOCK_DEPT_HTML = """
<html>
<body>
    <form name="f1">
        <input name="dept" value="CA200">
    </form>
    <a href="javascript:document.f1.submit();">心臟內科</a>
    <form name="f2">
        <input name="dept" value="CB110">
    </form>
    <a href="javascript:document.f2.submit();">一般外科</a>
</body>
</html>
"""

MOCK_SCHEDULE_HTML = """
<html>
<body>
    <a href="javascript:sub('area=3&dept=CA200&regType=1&choice_date=20260325&period=1&room=021&empNo=07931/黃漢倫','3','021');">黃漢倫</a>
    <a href="javascript:sub('area=3&dept=CA200&regType=1&choice_date=20260325&period=2&room=021&empNo=01234/測試醫師','3','021');"><font color="red">測試醫師(額滿)</font></a>
</body>
</html>
"""

MOCK_PROGRESS_HTML = """
<html>
<body>
    <table>
        <tr><td>021</td><td>黃漢倫</td><td>15</td><td>38</td></tr>
        <tr><td>022</td><td>測試醫師</td><td>0</td><td>10</td></tr>
    </table>
</body>
</html>
"""

@pytest.mark.asyncio
async def test_cgh_fetch_departments():
    scraper = CGHHsinchuScraper()
    async def mock_get(url, **kwargs):
        return MOCK_DEPT_HTML
    
    with patch.object(scraper, '_get', side_effect=mock_get):
        depts = await scraper.fetch_departments()
        assert len(depts) == 2
        assert depts[0].code == "CA200"
        assert depts[0].name == "心臟內科"
        assert depts[0].category == "內科系"

@pytest.mark.asyncio
async def test_cgh_fetch_schedule():
    scraper = CGHHsinchuScraper()
    
    async def mock_resp(url, data=None, **kwargs):
        if data and data.get("dept") == "CA200":
            return MOCK_SCHEDULE_HTML
        return ""

    with patch.object(scraper, '_get', AsyncMock(return_value="")):
        with patch.object(scraper, '_post', side_effect=mock_resp):
            slots = await scraper.fetch_schedule("CA200")
            assert len(slots) > 0
            
            slot1 = slots[0]
            assert slot1.doctor_name == "黃漢倫"
            assert slot1.doctor_no == "07931"
            assert slot1.session_date == date(2026, 3, 25)
            assert slot1.session_type == "上午"
            assert slot1.clinic_room == "021"
            assert slot1.is_full is False
            
            slot2 = slots[1]
            assert slot2.doctor_name == "測試醫師"
            assert slot2.is_full is True
            assert slot2.status == "額滿"

@pytest.mark.asyncio
async def test_cgh_fetch_clinic_progress():
    scraper = CGHHsinchuScraper()
    
    async def mock_post(url, data, **kwargs):
        if data and data.get("hosarea") == "3":
            return MOCK_PROGRESS_HTML
        return ""
    
    with patch.object(scraper, '_post', side_effect=mock_post):
        # By room
        progress = await scraper.fetch_clinic_progress("021", "1")
        assert progress is not None
        assert progress.current_number == 15
        assert progress.total_quota == 38
        
        # By doctor name
        progress2 = await scraper.fetch_clinic_progress("", "1", doctor_name="黃漢倫")
        assert progress2 is not None
        assert progress2.current_number == 15
        
        # Not found
        progress3 = await scraper.fetch_clinic_progress("999", "1")
        assert progress3 is None

def test_cgh_calculate_remaining_count():
    scraper = CGHHsinchuScraper()
    assert scraper.calculate_remaining_count(15, 20, []) == 5
