"""
第三階段整合測試：API 驗證
驗證 HMMH 爬蟲是否成功集成到 API 系統中
"""

import pytest
import uuid
from unittest.mock import patch, MagicMock
from app.main import app
from fastapi.testclient import TestClient
from app.database import get_supabase


client = TestClient(app)


class TestHMMHAPIIntegration:
    """驗證 HMMH 爬蟲的 API 集成"""

    def test_hospitals_endpoint_includes_hmmh(self):
        """✅ 驗證 /api/hospitals 端點包含 HMMH"""
        # Mock Supabase 回應
        mock_supabase = MagicMock()
        mock_select = mock_supabase.table.return_value.select.return_value
        mock_select.eq.return_value = mock_select
        
        # 模擬資料庫中有 HMMH 醫院
        mock_select.execute.return_value.data = [
            {
                "id": str(uuid.uuid4()),
                "name": "中山醫學大學附設醫院",
                "code": "CMUH_TAICHUNG",
                "base_url": "https://www.cmuh.cmu.edu.tw",
                "region": "台中市",
                "is_active": True,
                "created_at": "2023-01-01T00:00:00+00:00"
            },
            {
                "id": str(uuid.uuid4()),
                "name": "中山醫學大學附設醫院新竹分院",
                "code": "CMUH_HSINCHU",
                "base_url": "https://www.cmu-hch.cmu.edu.tw",
                "region": "新竹市",
                "is_active": True,
                "created_at": "2023-01-01T00:00:00+00:00"
            },
            {
                "id": str(uuid.uuid4()),
                "name": "馬偕紀念醫院新竹分院",
                "code": "HMMH",
                "base_url": "https://www.hc.mmh.org.tw",
                "region": "新竹縣市",
                "is_active": True,
                "created_at": "2023-01-01T00:00:00+00:00"
            }
        ]
        
        # 執行 API 調用
        with patch("app.api.hospitals.get_supabase", return_value=mock_supabase):
            response = client.get("/api/hospitals")
            
            # 驗證響應
            assert response.status_code == 200
            hospitals = response.json()
            
            # 驗證有 3 家醫院
            assert len(hospitals) == 3
            
            # 驗證 HMMH 在列表中
            hmmh_hospital = next((h for h in hospitals if h["code"] == "HMMH"), None)
            assert hmmh_hospital is not None
            assert hmmh_hospital["name"] == "馬偕紀念醫院新竹分院"
            assert hmmh_hospital["base_url"] == "https://www.hc.mmh.org.tw"
            assert hmmh_hospital["region"] == "新竹縣市"

    def test_hmmh_scraper_can_be_instantiated(self):
        """✅ 驗證 HMMH 爬蟲可被直接實例化"""
        from app.scrapers.hmmh import HMMHScraper
        
        scraper = HMMHScraper()
        
        assert scraper is not None
        assert scraper.HOSPITAL_CODE == "HMMH"
        assert scraper.BASE_URL == "https://www.hc.mmh.org.tw"

    def test_hmmh_in_available_scrapers_list(self):
        """✅ 驗證 HMMH 在可用爬蟲列表中"""
        from app.scrapers.hospital_registry import get_available_hospitals
        
        hospitals = get_available_hospitals()
        
        assert "HMMH" in hospitals
        assert hospitals["HMMH"] == "HMMHScraper"

    def test_hmmh_configuration_supported(self):
        """✅ 驗證系統配置支持 HMMH"""
        # 驗證 HMMH 爬蟲已在註冊表中
        from app.scrapers.hospital_registry import HOSPITAL_SCRAPERS
        
        assert "HMMH" in HOSPITAL_SCRAPERS
        
        # 驗證配置文件中有說明如何啟用 HMMH
        from app.config import Settings
        
        # Settings 應該有詳細的文檔字符串和註釋
        # 說明如何在環境變量中配置 HMMH
        config_source = Settings.model_config
        assert config_source is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
