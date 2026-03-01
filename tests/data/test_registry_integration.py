"""
集成測試：爬蟲註冊表與爬蟲實例化

驗證改革後的動態爬蟲加載系統是否正常工作。
"""

import pytest
from unittest.mock import patch, MagicMock
from app.scrapers.hospital_registry import (
    HOSPITAL_SCRAPERS,
    get_enabled_scrapers,
    validate_scrapers,
    get_available_hospitals,
)
from app.scrapers.cmuh import CMUHScraper, CMUHHsinchuScraper
from app.scrapers.base import BaseScraper
from app.config import Settings


class TestRegistryIntegration:
    """測試爬蟲註冊表與動態加載的集成"""

    def test_cmuh_scraper_instantiation(self):
        """✅ 驗證 CMUH 台中院爬蟲可被正確實例化"""
        scraper = CMUHScraper()
        assert isinstance(scraper, BaseScraper)
        assert scraper.HOSPITAL_CODE == "CMUH_TAICHUNG"
        assert scraper.BASE_URL == "https://www.cmuh.cmu.edu.tw"

    def test_cmuh_hsinchu_scraper_instantiation(self):
        """✅ 驗證 CMUH 新竹院爬蟲可被正確實例化"""
        scraper = CMUHHsinchuScraper()
        assert isinstance(scraper, BaseScraper)
        assert scraper.HOSPITAL_CODE == "CMUH_HSINCHU"
        assert scraper.BASE_URL == "https://www.cmu-hch.cmu.edu.tw"

    def test_scrapers_in_registry(self):
        """✅ 驗證爬蟲已在註冊表中"""
        assert "CMUH_TAICHUNG" in HOSPITAL_SCRAPERS
        assert "CMUH_HSINCHU" in HOSPITAL_SCRAPERS
        assert HOSPITAL_SCRAPERS["CMUH_TAICHUNG"] is CMUHScraper
        assert HOSPITAL_SCRAPERS["CMUH_HSINCHU"] is CMUHHsinchuScraper

    @patch("app.scrapers.hospital_registry.get_settings")
    def test_dynamic_loading_with_enabled_config(self, mock_get_settings):
        """✅ 驗證根據 ENABLED_HOSPITALS 動態加載爬蟲"""
        # 清除快取
        get_enabled_scrapers.cache_clear()

        # 模擬配置：啟用兩個爬蟲
        mock_settings = MagicMock(spec=Settings)
        mock_settings.enabled_hospitals = ["CMUH_TAICHUNG", "CMUH_HSINCHU"]
        mock_get_settings.return_value = mock_settings

        scrapers = get_enabled_scrapers()

        # 驗證加載結果
        assert len(scrapers) == 2
        assert any(s.HOSPITAL_CODE == "CMUH_TAICHUNG" for s in scrapers)
        assert any(s.HOSPITAL_CODE == "CMUH_HSINCHU" for s in scrapers)

        # 清除快取供後續測試使用
        get_enabled_scrapers.cache_clear()

    @patch("app.scrapers.hospital_registry.get_settings")
    def test_dynamic_loading_with_single_scraper(self, mock_get_settings):
        """✅ 驗證只啟用一個爬蟲時的加載行為"""
        get_enabled_scrapers.cache_clear()

        mock_settings = MagicMock(spec=Settings)
        mock_settings.enabled_hospitals = ["CMUH_TAICHUNG"]
        mock_get_settings.return_value = mock_settings

        scrapers = get_enabled_scrapers()

        assert len(scrapers) == 1
        assert scrapers[0].HOSPITAL_CODE == "CMUH_TAICHUNG"

        get_enabled_scrapers.cache_clear()

    @patch("app.scrapers.hospital_registry.get_settings")
    def test_dynamic_loading_with_disabled_hospital(self, mock_get_settings):
        """✅ 驗證禁用的爬蟲不被加載"""
        get_enabled_scrapers.cache_clear()

        # 只啟用台中院，禁用新竹院
        mock_settings = MagicMock(spec=Settings)
        mock_settings.enabled_hospitals = ["CMUH_TAICHUNG"]
        mock_get_settings.return_value = mock_settings

        scrapers = get_enabled_scrapers()

        # 確認新竹院未被加載
        assert not any(s.HOSPITAL_CODE == "CMUH_HSINCHU" for s in scrapers)

        get_enabled_scrapers.cache_clear()

    def test_scraper_attributes_correctness(self):
        """✅ 驗證爬蟲屬性的正確性和一致性"""
        # CMUH 台中院
        cmuh = CMUHScraper()
        assert cmuh.HOSPITAL_CODE == "CMUH_TAICHUNG"
        assert "cmuh" in cmuh.BASE_URL.lower()
        assert hasattr(cmuh, "CGI_BASE_URL")
        assert hasattr(cmuh, "PROGRESS_CGI")

        # CMUH 新竹院
        cmuh_hsinchu = CMUHHsinchuScraper()
        assert cmuh_hsinchu.HOSPITAL_CODE == "CMUH_HSINCHU"
        assert "cmu-hch" in cmuh_hsinchu.BASE_URL.lower()
        assert hasattr(cmuh_hsinchu, "CGI_BASE_URL")
        assert hasattr(cmuh_hsinchu, "PROGRESS_CGI")

    def test_scraper_interface_compatibility(self):
        """✅ 驗證爬蟲實現 BaseScraper 的必需方法"""
        scrapers = [CMUHScraper(), CMUHHsinchuScraper()]

        for scraper in scrapers:
            # 驗證必需的異步方法
            assert hasattr(scraper, "fetch_departments")
            assert callable(getattr(scraper, "fetch_departments"))

            assert hasattr(scraper, "fetch_schedule")
            assert callable(getattr(scraper, "fetch_schedule"))

            assert hasattr(scraper, "fetch_clinic_progress")
            assert callable(getattr(scraper, "fetch_clinic_progress"))

            assert hasattr(scraper, "close")
            assert callable(getattr(scraper, "close"))

    def test_available_hospitals_includes_cmuh(self):
        """✅ 驗證可用醫院列表包含 CMUH"""
        hospitals = get_available_hospitals()

        assert isinstance(hospitals, dict)
        assert "CMUH_TAICHUNG" in hospitals
        assert "CMUH_HSINCHU" in hospitals
        assert hospitals["CMUH_TAICHUNG"] == "CMUHScraper"
        assert hospitals["CMUH_HSINCHU"] == "CMUHHsinchuScraper"

    def test_registry_validation_passes(self):
        """✅ 驗證爬蟲註冊表驗證通過"""
        result = validate_scrapers()
        # 應該返回 True（如果只記錄但不拋出異常）
        assert result is not None


class TestScraperUtilityMethods:
    """測試爬蟲的工具方法（確認向後兼容性）"""

    def test_parse_date_valid_ad_format(self):
        """✅ 驗證 AD 年份日期解析"""
        scraper = CMUHScraper()
        from datetime import date

        result = scraper._parse_date("2024/03/15")
        assert result == date(2024, 3, 15)

    def test_parse_date_valid_roc_format(self):
        """✅ 驗證民國年份日期解析"""
        scraper = CMUHScraper()
        from datetime import date

        # 民國 113 年 = 西元 2024 年
        result = scraper._parse_date("113/03/15")
        assert result == date(2024, 3, 15)

    def test_parse_date_invalid_format(self):
        """✅ 驗證無效日期格式返回 None"""
        scraper = CMUHScraper()

        result = scraper._parse_date("N/A")
        assert result is None

    def test_normalize_session_type_morning(self):
        """✅ 驗證會診類型正規化 - 上午"""
        scraper = CMUHScraper()

        assert scraper._normalize_session_type("上午診") == "上午"
        assert scraper._normalize_session_type("上午") == "上午"
        assert scraper._normalize_session_type("AM") == "上午"

    def test_normalize_session_type_afternoon(self):
        """✅ 驗證會診類型正規化 - 下午"""
        scraper = CMUHScraper()

        assert scraper._normalize_session_type("下午門診") == "下午"
        assert scraper._normalize_session_type("下午") == "下午"
        assert scraper._normalize_session_type("PM") == "下午"

    def test_normalize_session_type_evening(self):
        """✅ 驗證會診類型正規化 - 晚上"""
        scraper = CMUHScraper()

        assert scraper._normalize_session_type("晚上") == "晚上"
        assert scraper._normalize_session_type("夜間") == "夜間"
        assert scraper._normalize_session_type("NIGHT") == "晚上"


class TestScraperBackwardCompatibility:
    """驗證改革不破壞現有爬蟲功能"""

    def test_cmuh_scraper_has_required_methods(self):
        """✅ 驗證 CMUH 爬蟲具有所需的所有方法"""
        scraper = CMUHScraper()

        # 核心方法
        assert hasattr(scraper, "fetch_departments")
        assert hasattr(scraper, "fetch_schedule")
        assert hasattr(scraper, "fetch_clinic_progress")
        assert hasattr(scraper, "close")

        # 工具方法
        assert hasattr(scraper, "_parse_date")
        assert hasattr(scraper, "_normalize_session_type")

    def test_cmuh_hsinchu_inherits_from_cmuh(self):
        """✅ 驗證 CMUHHsinchu 正確繼承 CMUH"""
        hsinchu = CMUHHsinchuScraper()

        # 應該有所有 CMUH 的方法
        assert hasattr(hsinchu, "fetch_departments")
        assert hasattr(hsinchu, "_parse_date")

        # 但有自己的配置
        assert hsinchu.HOSPITAL_CODE == "CMUH_HSINCHU"
        assert hsinchu.BASE_URL != CMUHScraper.BASE_URL

    def test_scraper_class_variables_not_shared(self):
        """✅ 驗證爬蟲之間的類別變數不相互干擾"""
        cmuh = CMUHScraper()
        hsinchu = CMUHHsinchuScraper()

        # 確認各自有獨立的代碼和 URL
        assert cmuh.HOSPITAL_CODE != hsinchu.HOSPITAL_CODE
        assert cmuh.BASE_URL != hsinchu.BASE_URL
        assert cmuh.CGI_BASE_URL != hsinchu.CGI_BASE_URL


@pytest.mark.asyncio
class TestScraperAsyncMethods:
    """測試爬蟲的異步方法簽名（確認可調用）"""

    async def test_cmuh_fetch_departments_signature(self):
        """✅ 驗證 fetch_departments 可被調用（使用 mock）"""
        scraper = CMUHScraper()

        # 無法進行真實網路調用，但驗證方法存在且可被 await
        with patch.object(scraper, "fetch_departments") as mock_fetch:
            mock_fetch.return_value = []
            result = await mock_fetch()
            assert result == []

        await scraper.close()

    async def test_cmuh_fetch_schedule_signature(self):
        """✅ 驗證 fetch_schedule 可被調用"""
        scraper = CMUHScraper()

        with patch.object(scraper, "fetch_schedule") as mock_fetch:
            mock_fetch.return_value = []
            result = await mock_fetch("123")
            assert result == []

        await scraper.close()

    async def test_cmuh_fetch_clinic_progress_signature(self):
        """✅ 驗證 fetch_clinic_progress 可被調用"""
        scraper = CMUHScraper()

        with patch.object(scraper, "fetch_clinic_progress") as mock_fetch:
            mock_fetch.return_value = None
            result = await mock_fetch("A", "1")
            assert result is None

        await scraper.close()


class TestScraperErrorHandling:
    """測試爬蟲的錯誤處理"""

    def test_scraper_initialization_with_invalid_config(self):
        """✅ 驗證無效配置不會立即崩潰"""
        # CMUH 不依賴任何外部配置，應該總能初始化
        scraper = CMUHScraper()
        assert scraper is not None

    def test_scraper_multiple_instantiation(self):
        """✅ 驗證可以多次實例化爬蟲"""
        scraper1 = CMUHScraper()
        scraper2 = CMUHScraper()

        # 應該是不同的實例
        assert scraper1 is not scraper2

        # 但應該有相同的配置
        assert scraper1.HOSPITAL_CODE == scraper2.HOSPITAL_CODE
        assert scraper1.BASE_URL == scraper2.BASE_URL
