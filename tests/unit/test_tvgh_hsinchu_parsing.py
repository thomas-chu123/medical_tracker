import pytest
import asyncio
from unittest.mock import MagicMock, patch
from app.scrapers.tvgh_hsinchu import TvghHsinchuScraper
from app.scrapers.base import DoctorSlot, ClinicProgress

@pytest.fixture
def scraper():
    return TvghHsinchuScraper()

@pytest.mark.asyncio
async def test_fetch_schedule_parsing(scraper):
    mock_html = """
    <html>
        <td>
            <form>
                <input name="doctorChineseName" value="測試醫師">
                <input name="consultDateAD" value="20260316">
                <input name="doctorNumber" value="1234">
                <input name="consultNoonFlag" value="M">
                <input name="consultRoomLocation" value="101">
            </form>
            <a href="#">已掛 15 / 可掛 50</a>
        </td>
    </html>
    """
    with patch.object(TvghHsinchuScraper, "_get", return_value=mock_html):
        slots = await scraper.fetch_schedule("DEPT1")
        assert len(slots) == 1
        slot = slots[0]
        assert slot.doctor_name == "測試"
        assert slot.registered == 15
        assert slot.total_quota == 50
        assert slot.is_full is False

@pytest.mark.asyncio
async def test_fetch_schedule_parsing_full(scraper):
    mock_html = """
    <html>
        <td>
            <form>
                <input name="doctorChineseName" value="滿人醫師">
                <input name="consultDateAD" value="20260316">
                <input name="doctorNumber" value="5678">
                <input name="consultNoonFlag" value="P">
                <input name="consultRoomLocation" value="202">
            </form>
            <a href="#">已掛 80 / 額滿 80</a>
        </td>
    </html>
    """
    with patch.object(TvghHsinchuScraper, "_get", return_value=mock_html):
        slots = await scraper.fetch_schedule("DEPT2")
        assert len(slots) == 1
        slot = slots[0]
        assert slot.registered == 80
        assert slot.total_quota == 80
        assert slot.is_full is True

@pytest.mark.asyncio
async def test_fetch_clinic_progress_parsing(scraper):
    mock_html = """
    <html>
        <body>
            <div id="header">
                <span>上午診</span>
            </div>
            <div class="panel">
                <div class="grid-item">
                    <table>
                        <tr>
                            <td>測試醫師 測試科</td>
                            <td>目前診號: 12 (掛號人數: 30)</td>
                        </tr>
                    </table>
                </div>
                <div class="grid-item">
                    <table>
                        <tr>
                            <td>比對醫師 內科</td>
                            <td>目前診號: 5 (人數: 10)</td>
                        </tr>
                    </table>
                </div>
            </div>
        </body>
    </html>
    """
    with patch.object(TvghHsinchuScraper, "_get", return_value=mock_html):
        # Test doctor name match
        progress = await scraper.fetch_clinic_progress(room="測試科", period="1", doctor_name="測試醫師")
        assert progress is not None
        assert progress.current_number == 12
        assert progress.registered_count == 30
        assert progress.status == "看診中"

        # Test partial doctor name match
        progress = await scraper.fetch_clinic_progress(room="測試科", period="1", doctor_name="測試")
        assert progress is not None
        assert progress.current_number == 12

        # Test department match
        progress = await scraper.fetch_clinic_progress(room="比對醫師", period="1")
        assert progress is not None
        assert progress.current_number == 5
        assert progress.registered_count == 10
