import pytest
from app.scrapers.tvgh_taichung import TVGHTaichungScraper

@pytest.mark.integration
class TestTVGHTaichungScraper:
    @pytest.fixture
    async def scraper(self):
        s = TVGHTaichungScraper()
        yield s
        await s.close()

    @pytest.mark.asyncio
    async def test_fetch_departments(self, scraper):
        depts = await scraper.fetch_departments()
        assert len(depts) > 0, "Should fetch at least one department"
        
        # Verify CM (Chest Medicine) exists as it's a common one listed
        dept_codes = [d.code for d in depts]
        assert "CM" in dept_codes, "CM department should exist"
        assert depts[0].hospital_code == "TVGH_TAICHUNG"

    @pytest.mark.asyncio
    async def test_fetch_schedule(self, scraper):
        # Using 'CM' as it's typically available
        slots = await scraper.fetch_schedule("CM")
        assert len(slots) > 0, "Should fetch at least one schedule slot for CM"
        
        slot = slots[0]
        assert slot.doctor_no is not None
        assert slot.doctor_name is not None
        assert slot.department_code == "CM"
        assert slot.session_type in ["上午", "下午", "晚上"]
        assert slot.clinic_room is not None

    @pytest.mark.asyncio
    async def test_fetch_clinic_progress(self, scraper):
        # Fetching schedule first to get a valid room/doctor
        slots = await scraper.fetch_schedule("CM")
        if not slots:
            pytest.skip("No slots available to test progress")
            
        slot = slots[0]
        
        # Test progress fetch (may return None if not today or not opened)
        progress = await scraper.fetch_clinic_progress(
            room=slot.clinic_room,
            period="1", # Using 1 for morning just to test the endpoint
            dept_code=slot.department_code,
            doctor_name=slot.doctor_name
        )
        
        # We don't assert it's NOT None because it depends on the time of day,
        # but if it returns something, it should be a ClinicProgress object.
        if progress:
            assert progress.clinic_room is not None
            assert progress.session_type in ["上午", "下午", "晚上"]
            assert progress.current_number is not None
