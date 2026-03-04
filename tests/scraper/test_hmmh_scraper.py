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
MOCK_HMMH_DEPT_HTML = """
<!DOCTYPE html>
<html>
<body>
<a href="register_divide.php?depid=1">內科</a>
<a href="register_divide.php?depid=2">外科</a>
<a href="register_divide.php?depid=3">兒科</a>
<a href="register_divide.php?depid=4">婦產科</a>
<a href="register_divide.php?depid=5">骨科</a>
<a href="register_divide.php?depid=6">神經科</a>
<a href="register_divide.php?depid=7">精神科</a>
<a href="register_divide.php?depid=8">耳鼻喉科</a>
<a href="register_divide.php?depid=9">眼科</a>
<a href="register_divide.php?depid=10">牙科</a>
<a href="register_divide.php?depid=11">皮膚科</a>
<a href="register_divide.php?depid=12">復健科</a>
<a href="register_divide.php?depid=13">泌尿科</a>
<a href="register_divide.php?depid=14">一般外科</a>
<a href="register_divide.php?depid=15">胃腸科</a>
<a href="register_divide.php?depid=16">心臟科</a>
<a href="register_divide.php?depid=17">胸腔科</a>
<a href="register_divide.php?depid=18">腎臟科</a>
<a href="register_divide.php?depid=19">新陳代謝科</a>
<a href="register_divide.php?depid=20">免疫風濕科</a>
<a href="register_divide.php?depid=21">家醫科</a>
<a href="register_divide.php?depid=22">感染科</a>
<a href="register_divide.php?depid=23">腫瘤科</a>
<a href="register_divide.php?depid=24">放射腫瘤科</a>
<a href="register_divide.php?depid=25">血液腫瘤科</a>
<a href="register_divide.php?depid=26">神經外科</a>
<a href="register_divide.php?depid=27">整形外科</a>
<a href="register_divide.php?depid=28">中醫科</a>
<a href="register_divide.php?depid=29">麻醉科</a>
<a href="register_divide.php?depid=30">物理治療科</a>
<a href="register_divide.php?depid=31">營養室</a>
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
<table>
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
    <td>江瑞凡 4948 靜脈曲張特診</td>
    <td></td>
    <td>陳志軒 5022</td>
    <td>李健仁 4875 含肛腸</td>
    <td></td>
    <td></td>
  </tr>
  <tr>
    <td>15</td>
    <td>吳宥達 4873 含甲狀腺</td>
    <td>陳永成 4864</td>
    <td></td>
    <td>謝復興 5023</td>
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

