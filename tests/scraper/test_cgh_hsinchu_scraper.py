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
    <form name="sec1">
        <input name="sec" value="1">
        <input name="room" value="021">
        <input name="week" value="1">
        <input name="deptn" value="心臟內科">
    </form>
    <a href="javascript:sub(document.sec1,'07931/黃漢倫','3','021');">黃漢倫</a>
    <form name="sec2">
        <input name="sec" value="2">
        <input name="room" value="021">
        <input name="week" value="1">
        <input name="deptn" value="心臟內科">
    </form>
    <a href="javascript:sub(document.sec2,'01234/測試醫師','3','021');"><font color="red">測試醫師(額滿)</font></a>
</body>
</html>
"""

MOCK_PROGRESS_HTML = """
<html>
<body>
    <table>
        <tr>
            <td>目前看診序號：15</td>
        </tr>
        <tr>
            <td>診間</td>
            <td>醫生</td>
            <td>當前號</td>
            <td>總號</td>
        </tr>
        <tr>
            <td>021</td>
            <td>黃漢倫</td>
            <td>15</td>
            <td>38</td>
        </tr>
        <tr>
            <td>尚未就診病人號碼：</td>
            <td>1</td><td>3</td><td>6</td><td>8</td><td>10</td>
            <td>12</td><td>14</td><td>19</td><td>20</td><td>21</td>
            <td>22</td><td>23</td><td>24</td><td>25</td><td>26</td>
            <td>27</td><td>28</td>
        </tr>
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
    
    MOCK_DEPT_LIST_HTML = """
    <html><body>
        <form name="f1">
            <input name="dept" value="CA200">
        </form>
        <a>心臟內科</a>
    </body></html>
    """
    
    MOCK_DATES_HTML = "115.03.25 115.03.26"  # ROC dates that will be converted
    
    async def mock_resp(url, data=None, **kwargs):
        if "main_01.jsp" in url and data and data.get("dept") == "CA200":
            return MOCK_SCHEDULE_HTML
        elif "main_02.jsp" in url:
            # Return date strings for the second POST request
            return MOCK_DATES_HTML
        elif "main_01.jsp" in url:
            return MOCK_DEPT_LIST_HTML
        return ""

    with patch.object(scraper, '_get', AsyncMock(side_effect=mock_resp)):
        with patch.object(scraper, '_post', side_effect=mock_resp):
            slots = await scraper.fetch_schedule("CA200")
            assert len(slots) >= 2
            
            # Find the first doctor's first slot (黃漢倫, 上午)
            slot_huang = next((s for s in slots if s.doctor_name == "黃漢倫" and s.session_type == "上午"), None)
            assert slot_huang is not None
            assert slot_huang.doctor_no == "07931"
            assert slot_huang.clinic_room == "021"
            assert slot_huang.is_full is False
            
            # Find the second doctor's first slot (測試醫師, 下午)
            slot_test = next((s for s in slots if s.doctor_name == "測試醫師" and s.session_type == "下午"), None)
            assert slot_test is not None
            assert slot_test.is_full is True
            assert slot_test.status == "額滿"

@pytest.mark.asyncio
async def test_cgh_fetch_clinic_progress():
    scraper = CGHHsinchuScraper()
    
    async def mock_post(url, data, **kwargs):
        # Return MOCK_PROGRESS_HTML for all clinic progress queries
        if data and data.get("hosarea") == "3":
            return MOCK_PROGRESS_HTML
        return ""
    
    with patch.object(scraper, '_post', side_effect=mock_post):
        # By room
        progress = await scraper.fetch_clinic_progress("021", "1")
        assert progress is not None
        assert progress.current_number == 15
        # total_quota is calculated as the max of queue numbers: [1,3,6,8,10,12,14,19,20,21,22,23,24,25,26,27,28]
        assert progress.total_quota == 28
        
        # By doctor name (room is empty, so should match by doctor name in HTML)
        progress2 = await scraper.fetch_clinic_progress("", "1", doctor_name="黃漢倫")
        assert progress2 is not None
        assert progress2.current_number == 15
        
        # Not found - return empty HTML for room 999
        # Modify mock to return empty HTML when room is not 021
        
        async def mock_post_not_found(url, data, **kwargs):
            if data and data.get("hosarea") == "3" and data.get("room") == "021":
                return MOCK_PROGRESS_HTML
            return ""
        
        with patch.object(scraper, '_post', side_effect=mock_post_not_found):
            progress3 = await scraper.fetch_clinic_progress("999", "1")
            assert progress3 is None

def test_cgh_calculate_remaining_count():
    scraper = CGHHsinchuScraper()
    assert scraper.calculate_remaining_count(15, 20, []) == 5
