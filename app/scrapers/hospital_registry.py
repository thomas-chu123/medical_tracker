"""
醫院爬蟲註冊中心（Hospital Scraper Registry）

本模組提供統一的爬蟲管理機制，通過配置驅動的方式動態加載啟用的醫院爬蟲。
這樣可以：
1. 解耦 scheduler 與具體醫院爬蟲
2. 支持動態啟用/禁用醫院
3. 簡化新增醫院的流程

架構：
- HOSPITAL_SCRAPERS: 所有可用爬蟲的註冊表
- get_enabled_scrapers(): 根據配置動態加載啟用的爬蟲
- validate_scrapers(): 驗證所有爬蟲配置的有效性

新增醫院流程：
1. 在 scrapers/ 目錄建立爬蟲類別，繼承 BaseScraper
2. 在 HOSPITAL_SCRAPERS 中添加一行映射
3. 在 .env 的 ENABLED_HOSPITALS 中啟用
"""

from typing import Dict, Type, List
from functools import lru_cache
from app.scrapers.base import BaseScraper
from app.scrapers.cmuh import CMUHScraper, CMUHHsinchuScraper
from app.scrapers.ntuh import NTUHHsinchuScraper
from app.scrapers.hmmh import HMMHScraper
from app.config import get_settings
import logging

logger = logging.getLogger(__name__)

# 爬蟲註冊表：medical_tracker_code -> Scraper 類別
# 新增醫院時，只需在此添加一行映射
HOSPITAL_SCRAPERS: Dict[str, Type[BaseScraper]] = {
    "CMUH_TAICHUNG": CMUHScraper,           # 中榮台中院
    "CMUH_HSINCHU": CMUHHsinchuScraper,    # 中榮新竹院
    "NTUH_HSINCHU": NTUHHsinchuScraper,    # 台大新竹分院
    "HMMH": HMMHScraper,                   # 馬偕新竹分院
    # "HSINCHU_HOSPITAL": HsinchuHospitalScraper,  # 未來範例
}


@lru_cache(maxsize=1)
def get_enabled_scrapers() -> List[BaseScraper]:
    """
    根據環境變數配置動態加載啟用的爬蟲。

    流程：
    1. 從 ENABLED_HOSPITALS 環境變數讀取啟用的醫院代碼列表
    2. 遍歷代碼，在 HOSPITAL_SCRAPERS 中查找對應的爬蟲類別
    3. 實例化並回傳

    使用 @lru_cache(maxsize=1) 避免重複實例化。

    Returns:
        List[BaseScraper]: 啟用的爬蟲實例列表

    Raises:
        無 - 無效的醫院代碼會被忽略並記錄警告

    Example:
        >>> scrapers = get_enabled_scrapers()
        >>> print(f"Enabled hospitals: {len(scrapers)}")
        Enabled hospitals: 2
    """
    settings = get_settings()
    enabled_hospitals = settings.enabled_hospitals

    logger.info(
        f"[Registry] Loading scrapers for hospitals: {', '.join(enabled_hospitals)}"
    )

    scrapers = []
    for hospital_code in enabled_hospitals:
        if hospital_code in HOSPITAL_SCRAPERS:
            scraper_class = HOSPITAL_SCRAPERS[hospital_code]
            try:
                scraper = scraper_class()
                scrapers.append(scraper)
                logger.debug(f"[Registry] Loaded {hospital_code}: {scraper_class.__name__}")
            except Exception as e:
                logger.error(
                    f"[Registry] Failed to instantiate scraper for {hospital_code}: {e}"
                )
        else:
            logger.warning(
                f"[Registry] Unknown hospital code '{hospital_code}'. "
                f"Available: {', '.join(HOSPITAL_SCRAPERS.keys())}"
            )

    if not scrapers:
        logger.error("[Registry] No scrapers loaded! Check ENABLED_HOSPITALS configuration.")

    return scrapers


def validate_scrapers() -> bool:
    """
    驗證所有已註冊的爬蟲是否有有效的 HOSPITAL_CODE。

    檢查項目：
    1. 每個爬蟲類別都定義了 HOSPITAL_CODE
    2. HOSPITAL_CODE 非空
    3. 記錄所有已註冊的醫院

    Returns:
        bool: 所有爬蟲都有效時回傳 True，否則回傳 False

    Example:
        >>> if not validate_scrapers():
        ...     logger.error("Invalid scraper configuration")
        ...     sys.exit(1)
    """
    logger.info("[Registry] Validating scraper configuration...")
    all_valid = True

    for hospital_code, scraper_class in HOSPITAL_SCRAPERS.items():
        try:
            # 檢查爬蟲類別是否有 HOSPITAL_CODE 屬性
            if not hasattr(scraper_class, "HOSPITAL_CODE"):
                logger.error(f"[Registry] {scraper_class.__name__} missing HOSPITAL_CODE attribute")
                all_valid = False
                continue

            scraper_code = scraper_class.HOSPITAL_CODE
            if not scraper_code or not isinstance(scraper_code, str):
                logger.error(
                    f"[Registry] {scraper_class.__name__} has invalid HOSPITAL_CODE: {scraper_code}"
                )
                all_valid = False
                continue

            logger.info(f"[Registry] ✓ {hospital_code}: {scraper_class.__name__}")

        except Exception as e:
            logger.error(f"[Registry] Error validating {hospital_code}: {e}")
            all_valid = False

    return all_valid


def get_available_hospitals() -> Dict[str, str]:
    """
    取得所有可用醫院的信息。

    Returns:
        Dict[str, str]: 醫院代碼 -> 爬蟲類別名稱的映射

    Example:
        >>> hospitals = get_available_hospitals()
        >>> print(hospitals)
        {'CMUH_TAICHUNG': 'CMUHScraper', 'CMUH_HSINCHU': 'CMUHHsinchuScraper'}
    """
    return {code: scraper.__name__ for code, scraper in HOSPITAL_SCRAPERS.items()}
