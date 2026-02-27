import pytest
from unittest.mock import MagicMock, AsyncMock
from datetime import date
from app.scrapers.base import DoctorSlot, ClinicProgress
import os
import logging
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service


logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# SELENIUM FIXTURES
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="session")
def selenium_config():
    """共用的 Selenium 配置"""
    return {
        "base_url": os.getenv("TEST_BASE_URL", "http://localhost:8000"),
        "headless": os.getenv("SELENIUM_HEADLESS", "true").lower() == "true",
        "implicit_wait": 10,
        "explicit_wait": 20,
    }


@pytest.fixture
def chrome_driver(selenium_config):
    """建立 Chrome WebDriver"""
    chrome_options = Options()
    
    if selenium_config["headless"]:
        chrome_options.add_argument("--headless")
    
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.implicitly_wait(selenium_config["implicit_wait"])
    
    yield driver
    
    # 清理
    driver.quit()


@pytest.fixture
def wait_driver(chrome_driver, selenium_config):
    """包含顯式等待的 WebDriver"""
    return WebDriverWait(chrome_driver, selenium_config["explicit_wait"])


@pytest.fixture
def browser(chrome_driver, selenium_config):
    """瀏覽器訪問助手"""
    class Browser:
        def __init__(self, driver, config):
            self.driver = driver
            self.config = config
        
        def navigate_to(self, path: str = ""):
            url = f"{self.config['base_url']}{path}"
            logger.info(f"🌐 Navigating to: {url}")
            self.driver.get(url)
        
        def screenshot(self, filename: str):
            path = f"tests/screenshots/{filename}.png"
            os.makedirs("tests/screenshots", exist_ok=True)
            self.driver.save_screenshot(path)
            logger.info(f"📸 Screenshot saved: {path}")
        
        def page_title(self) -> str:
            return self.driver.title
        
        def current_url(self) -> str:
            return self.driver.current_url
    
    return Browser(chrome_driver, selenium_config)


# ══════════════════════════════════════════════════════════════════════════════
# EXISTING FIXTURES
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_supabase():
    mock = MagicMock()
    # Mock some common chains
    mock.table.return_value.select.return_value.execute.return_value.data = []
    mock.table.return_value.insert.return_value.execute.return_value.data = []
    return mock

@pytest.fixture
def mock_settings():
    from app.config import Settings
    return Settings(
        supabase_url="https://test.supabase.co",
        supabase_key="test-key",
        line_notify_client_id="id",
        line_notify_client_secret="secret",
        smtp_server="localhost",
        smtp_port=1025,
        smtp_user="test@example.com",
        smtp_password="password",
        admin_email="admin@example.com"
    )

@pytest.fixture
def sample_doctor_slot():
    return DoctorSlot(
        doctor_no="D6351",
        doctor_name="孟志瀚",
        department_code="0600",
        session_date=date.today(),
        session_type="上午",
        total_quota=50,
        registered=45,
        clinic_room="230"
    )

@pytest.fixture
def sample_clinic_progress():
    return ClinicProgress(
        clinic_room="230",
        session_type="上午",
        current_number=37,
        total_quota=50,
        registered_count=48,
        status="看診中"
    )
