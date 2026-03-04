"""
Test script for HMMH scraper

Usage:
    python -m pytest tests/scraper/test_hmmh_scraper.py -xvs
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch
from bs4 import BeautifulSoup
from app.scrapers.hmmh import HMMHScraper

# Mock HTML for department list
# Matches the actual progress.php structure: <form action="progressstatus.php">
# with <select name="dept"> containing all departments (server-rendered, no AJAX)
MOCK_HMMH_DEPT_HTML = """
<!DOCTYPE html>
<html lang="zh-tw">
<body>
<form method="GET" id="progress" name="progress" action="progressstatus.php">
    <select id="select-dept" name="dept" class="select">
        <option value="">請選擇</option>
        <option value='12'>內科部-內分泌暨新陳代謝科</option>
        <option value='13'>內科部-胃腸肝膽科</option>
        <option value='14'>內科部-心臟內科</option>
        <option value='15'>內科部-胸腔內科</option>
        <option value='16'>內科部-腎臟內科</option>
        <option value='18'>內科部-血液腫瘤科</option>
        <option value='19'>內科部-過敏免疫風濕科</option>
        <option value='26'>內科部-感染科</option>
        <option value='1G'>內科部-老年醫學科</option>
        <option value='20'>其他科系-神經內科</option>
        <option value='21'>其他科系-精神科</option>
        <option value='24'>其他科系-皮膚科</option>
        <option value='70'>其他科系-眼科</option>
        <option value='71'>其他科系-耳鼻喉頭頸外科</option>
        <option value='72'>其他科系-牙科</option>
        <option value='73'>其他科系-復健科</option>
        <option value='50'>外科部-一般外科</option>
        <option value='51'>外科部-小兒外科</option>
        <option value='52'>外科部-骨科</option>
        <option value='53'>外科部-神經外科</option>
        <option value='54'>外科部-泌尿科</option>
        <option value='55'>外科部-整形外科</option>
        <option value='57'>外科部-乳房外科</option>
        <option value='90'>婦兒部-婦產科</option>
        <option value='95'>婦兒部-兒科</option>
    </select>
    <select id="select-ap" name="ap" class="select">
        <option value="">請選擇看診時段</option>
        <option value="1">上午診</option>
        <option value="2">下午診</option>
        <option value="3">夜間診</option>
    </select>
</form>
</body>
</html>
"""


@pytest.mark.asyncio
async def test_fetch_departments():
    """Test fetching department list with mocked HTML"""
    
    scraper = HMMHScraper()
    
    # Mock the _get method to return test HTML
    async def mock_get(url, **kwargs):
        return MOCK_HMMH_DEPT_HTML
    
    try:
        with patch.object(scraper, '_get', side_effect=mock_get):
            # Call actual method
            depts = await scraper.fetch_departments()
            
            print(f"\n✅ Found {len(depts)} departments via scraper\n")
            
            # Verify we got departments
            assert len(depts) > 0, "Should find at least one department"
            assert depts[0].code is not None
            assert depts[0].name is not None
            
            # Print first 10 departments
            for i, dept in enumerate(depts[:10], 1):
                print(f"{i:2d}. [{dept.code:3s}] {dept.name:20s} - {dept.category}")
            
            if len(depts) > 10:
                print(f"... and {len(depts) - 10} more departments")
            
            return depts
    finally:
        await scraper.close()


# Mock HTML for schedule
MOCK_HMMH_SCHEDULE_HTML = """
<!DOCTYPE html>
<html>
<body>
<table id="tblSch">
  <tr>
    <th>診間</th>
    <th colspan="3">星期一</th>
    <th colspan="3">星期二</th>
  </tr>
  <tr>
    <th></th>
    <th>上午</th>
    <th>下午</th>
    <th>晚上</th>
    <th>上午</th>
    <th>下午</th>
    <th>晚上</th>
  </tr>
  <tr>
    <td>14</td>
    <td><a onclick="registergo('68','4948')">江瑞凡 4948 靜脈曲張特診</a></td>
    <td></td>
    <td><a onclick="registergo('68','5022')">陳志軒 5022</a></td>
    <td><a onclick="registergo('68','4875')">李健仁 4875 含肛腸</a></td>
    <td></td>
    <td></td>
  </tr>
  <tr>
    <td>15</td>
    <td><a onclick="registergo('68','4873')">吳宥達 4873 含甲狀腺</a></td>
    <td><a onclick="registergo('68','4864')">陳永成 4864</a></td>
    <td></td>
    <td><a onclick="registergo('68','5023')">謝復興 5023</a></td>
    <td></td>
    <td></td>
  </tr>
</table>
</body>
</html>
"""


@pytest.mark.asyncio
async def test_fetch_clinic_progress():
    """Test fetching clinic progress with mocked HTML"""
    
    scraper = HMMHScraper()
    
    # Mock the _get method
    async def mock_get(url, **kwargs):
        # Return None to simulate no progress table (outside clinic hours)
        return """<html><body>尚未開始看診</body></html>"""
    
    try:
        with patch.object(scraper, '_get', side_effect=mock_get):
            # Call actual method
            progress = await scraper.fetch_clinic_progress("14", "1")
            
            # Should return None when no progress data available
            print(f"\n⚠️  Clinic progress: {progress}")
            assert progress is None or progress.current_number is not None, \
                "Should return None or valid progress object"
    finally:
        await scraper.close()


@pytest.mark.asyncio
async def test_fetch_schedule():
    """Test fetching doctor schedule with mocked HTML"""
    
    scraper = HMMHScraper()
    
    # Mock the _get method to return test HTML
    async def mock_get(url, **kwargs):
        return MOCK_HMMH_SCHEDULE_HTML
    
    try:
        with patch.object(scraper, '_get', side_effect=mock_get):
            # Call actual method
            slots = await scraper.fetch_schedule("14")
            
            print(f"\n✅ Found {len(slots)} doctor slots")
            
            # Verify we got slots
            assert len(slots) > 0, "Should find at least one doctor slot"
            
            # Verify slot structure
            for slot in slots[:5]:
                assert slot.doctor_name is not None
                assert slot.doctor_no is not None
                assert slot.session_date is not None
                assert slot.session_type in ["上午", "下午", "晚上"]
                print(f"  {slot.doctor_name:8s} ({slot.doctor_no:4s}) "
                      f"@ {slot.session_date} {slot.session_type:2s}")
            
            if len(slots) > 5:
                print(f"  ... and {len(slots) - 5} more slots")
            
            return slots
    finally:
        await scraper.close()

