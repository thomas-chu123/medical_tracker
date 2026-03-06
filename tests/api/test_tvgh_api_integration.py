"""
API Integration tests for TVGH_HSINCHU
"""

import pytest
import uuid
from unittest.mock import patch, MagicMock
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)

class TestTvghHsinchuAPIIntegration:
    def test_hospitals_endpoint_includes_tvgh(self):
        """Verify /api/hospitals endpoint includes TVGH_HSINCHU"""
        mock_supabase = MagicMock()
        mock_select = mock_supabase.table.return_value.select.return_value
        mock_select.eq.return_value = mock_select
        
        mock_select.execute.return_value.data = [
            {
                "id": str(uuid.uuid4()),
                "name": "臺北榮民總醫院新竹分院",
                "code": "TVGH_HSINCHU",
                "base_url": "https://webreg.vhct.gov.tw",
                "region": "新竹縣市",
                "is_active": True,
                "created_at": "2023-01-01T00:00:00+00:00"
            }
        ]
        
        with patch("app.api.hospitals.get_supabase", return_value=mock_supabase):
            response = client.get("/api/hospitals")
            
            assert response.status_code == 200
            hospitals = response.json()
            
            tvgh_hospital = next((h for h in hospitals if h["code"] == "TVGH_HSINCHU"), None)
            assert tvgh_hospital is not None
            assert tvgh_hospital["name"] == "臺北榮民總醫院新竹分院"
            assert tvgh_hospital["base_url"] == "https://webreg.vhct.gov.tw"
            assert tvgh_hospital["region"] == "新竹縣市"

    def test_tvgh_hsinchu_scraper_can_be_instantiated(self):
        """Verify scraper logic class loading"""
        from app.scrapers.tvgh_hsinchu import TvghHsinchuScraper
        scraper = TvghHsinchuScraper()
        
        assert scraper is not None
        assert scraper.HOSPITAL_CODE == "TVGH_HSINCHU"
        assert scraper.BASE_URL == "https://webreg.vhct.gov.tw"

    def test_tvgh_hsinchu_in_available_scrapers_list(self):
        """Verify TVGH_HSINCHU registered in available factory"""
        from app.scrapers.hospital_registry import get_available_hospitals
        
        hospitals = get_available_hospitals()
        
        assert "TVGH_HSINCHU" in hospitals
        assert hospitals["TVGH_HSINCHU"] == "TvghHsinchuScraper"

    def test_tvgh_hsinchu_configuration_supported(self):
        """Verify configuration supports TVGH_HSINCHU"""
        from app.scrapers.hospital_registry import HOSPITAL_SCRAPERS
        assert "TVGH_HSINCHU" in HOSPITAL_SCRAPERS
        
        from app.config import get_settings
        settings = get_settings()
        assert "TVGH_HSINCHU" in settings.enabled_hospitals

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
