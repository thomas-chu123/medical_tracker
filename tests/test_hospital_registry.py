"""
醫院爬蟲註冊中心單元測試

測試 app/scrapers/hospital_registry 模組的功能：
1. 爬蟲註冊表完整性
2. 動態爬蟲加載
3. 配置驗證
4. 快取機制
"""

import pytest
from unittest.mock import patch, MagicMock
from app.scrapers.hospital_registry import (
    HOSPITAL_SCRAPERS,
    get_enabled_scrapers,
    validate_scrapers,
    get_available_hospitals,
)
from app.scrapers.base import BaseScraper


class TestHospitalRegistry:
    """爬蟲註冊中心測試套件"""

    def test_hospital_scrapers_not_empty(self):
        """驗證至少有一個註冊的爬蟲"""
        assert len(HOSPITAL_SCRAPERS) > 0, "HOSPITAL_SCRAPERS 不應為空"

    def test_all_scrapers_inherit_base(self):
        """驗證所有註冊的爬蟲都繼承自 BaseScraper"""
        for hospital_code, scraper_class in HOSPITAL_SCRAPERS.items():
            assert issubclass(
                scraper_class, BaseScraper
            ), f"{hospital_code} 的爬蟲 {scraper_class.__name__} 不是 BaseScraper 的子類"

    def test_all_scrapers_have_hospital_code(self):
        """驗證所有爬蟲都定義了 HOSPITAL_CODE"""
        for hospital_code, scraper_class in HOSPITAL_SCRAPERS.items():
            assert hasattr(
                scraper_class, "HOSPITAL_CODE"
            ), f"{scraper_class.__name__} 缺少 HOSPITAL_CODE 屬性"
            assert (
                scraper_class.HOSPITAL_CODE
            ), f"{scraper_class.__name__} 的 HOSPITAL_CODE 為空"

    def test_get_available_hospitals_returns_dict(self):
        """驗證 get_available_hospitals() 回傳字典"""
        hospitals = get_available_hospitals()
        assert isinstance(hospitals, dict)
        assert len(hospitals) == len(HOSPITAL_SCRAPERS)

    def test_get_available_hospitals_content(self):
        """驗證 get_available_hospitals() 包含所有醫院"""
        hospitals = get_available_hospitals()
        for code, name in hospitals.items():
            assert code in HOSPITAL_SCRAPERS
            assert name == HOSPITAL_SCRAPERS[code].__name__

    @patch("app.scrapers.hospital_registry.get_settings")
    def test_get_enabled_scrapers_respects_config(self, mock_settings):
        """驗證 get_enabled_scrapers() 尊重配置"""
        # 清除快取
        get_enabled_scrapers.cache_clear()

        # 模擬配置只啟用第一家醫院
        mock_settings.return_value.enabled_hospitals = [list(HOSPITAL_SCRAPERS.keys())[0]]

        scrapers = get_enabled_scrapers()
        assert len(scrapers) == 1
        assert isinstance(scrapers[0], list(HOSPITAL_SCRAPERS.values())[0])

        # 清除快取
        get_enabled_scrapers.cache_clear()

    @patch("app.scrapers.hospital_registry.get_settings")
    def test_get_enabled_scrapers_handles_empty_config(self, mock_settings):
        """驗證 get_enabled_scrapers() 處理空配置"""
        # 清除快取
        get_enabled_scrapers.cache_clear()

        mock_settings.return_value.enabled_hospitals = []
        scrapers = get_enabled_scrapers()
        assert scrapers == []

        # 清除快取
        get_enabled_scrapers.cache_clear()

    @patch("app.scrapers.hospital_registry.get_settings")
    def test_get_enabled_scrapers_handles_invalid_codes(self, mock_settings):
        """驗證 get_enabled_scrapers() 處理無效的醫院代碼"""
        # 清除快取
        get_enabled_scrapers.cache_clear()

        # 混合有效和無效的代碼
        valid_code = list(HOSPITAL_SCRAPERS.keys())[0]
        mock_settings.return_value.enabled_hospitals = [valid_code, "INVALID_CODE"]

        scrapers = get_enabled_scrapers()
        # 應該只加載有效的爬蟲
        assert len(scrapers) == 1

        # 清除快取
        get_enabled_scrapers.cache_clear()

    @patch("app.scrapers.hospital_registry.get_settings")
    def test_get_enabled_scrapers_caching(self, mock_settings):
        """驗證 @lru_cache 快取機制正常工作"""
        # 清除快取
        get_enabled_scrapers.cache_clear()

        mock_settings.return_value.enabled_hospitals = [
            list(HOSPITAL_SCRAPERS.keys())[0]
        ]

        # 第一次調用
        scrapers1 = get_enabled_scrapers()

        # 第二次調用應該返回相同的對象（快取）
        scrapers2 = get_enabled_scrapers()

        # 因為使用了快取，應該是同一個對象
        assert scrapers1 is scrapers2

        # 清除快取
        get_enabled_scrapers.cache_clear()

    def test_validate_scrapers_all_valid(self):
        """驗證所有已註冊的爬蟲都有效"""
        # 這個測試會檢查當前註冊表中的所有爬蟲
        result = validate_scrapers()
        # 應該回傳 True（所有爬蟲都有效）
        assert result is True

    def test_hospital_scrapers_registry_keys(self):
        """驗證註冊表的鍵值格式一致"""
        for code in HOSPITAL_SCRAPERS.keys():
            # 鍵應該是大寫，用下劃線分隔
            assert code.isupper() or "_" in code, f"醫院代碼 {code} 格式不規範"


class TestScraperInstantiation:
    """爬蟲實例化測試"""

    def test_all_scrapers_can_instantiate(self):
        """驗證所有爬蟲類別都可以實例化"""
        for hospital_code, scraper_class in HOSPITAL_SCRAPERS.items():
            try:
                scraper = scraper_class()
                assert scraper is not None
                # 驗證實例化後有 HOSPITAL_CODE 屬性
                assert hasattr(scraper, "HOSPITAL_CODE")
            except Exception as e:
                pytest.fail(f"無法實例化 {hospital_code}: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
