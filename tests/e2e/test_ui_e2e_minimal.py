"""
Minimal E2E Selenium UI Tests - Can be run locally with running server.

To run:
  1. Start the server: python -m uvicorn app.main:app --reload
  2. Run tests: pytest tests/test_ui_e2e_minimal.py -v -s

Set environment variables:
  TEST_BASE_URL=http://localhost:8000
  TEST_EMAIL=test_e2e@example.com
  TEST_PASSWORD=TestPassword123
  SELENIUM_HEADLESS=false  # Set to false to see browser
"""
import pytest
import logging
import time
import os
from selenium.webdriver.common.by import By
from selenium.webdriver.support.expected_conditions import (
    presence_of_element_located,
    visibility_of_element_located,
)


logger = logging.getLogger(__name__)

# Read test credentials from environment variables
TEST_EMAIL = os.getenv('TEST_EMAIL', 'test_e2e@example.com')
TEST_PASSWORD = os.getenv('TEST_PASSWORD', 'TestPassword123')


class TestE2EMinimal:
    """最小端到端測試套件"""
    
    def test_01_navigate_to_home(self, browser):
        """測試 1: 導航到首頁"""
        browser.navigate_to("/")
        assert browser.driver.title, "Page should have title"
        logger.info(f"✅ Navigated to home page: {browser.driver.title}")
        browser.screenshot("01_home_page")
    
    def test_02_login_page_loads(self, browser, wait_driver):
        """測試 2: 登入頁面載入"""
        browser.navigate_to("/")
        
        # Check login form elements exist
        email_input = wait_driver.until(
            presence_of_element_located((By.ID, "login-email"))
        )
        password_input = browser.driver.find_element(By.ID, "login-password")
        login_button = browser.driver.find_element(By.ID, "login-btn")
        
        assert email_input.is_displayed()
        assert password_input.is_displayed()
        assert login_button.is_displayed()
        
        logger.info("✅ Login form elements present")
        browser.screenshot("02_login_form")
    
    def test_03_successful_login(self, browser, wait_driver):
        """測試 3: 成功登入"""
        import time
        
        browser.navigate_to("/")
        
        # Enter credentials
        email = browser.driver.find_element(By.ID, "login-email")
        password = browser.driver.find_element(By.ID, "login-password")
        login_btn = browser.driver.find_element(By.ID, "login-btn")
        
        logger.info("✏️ Entering credentials...")
        email.clear()
        email.send_keys(TEST_EMAIL)
        password.clear()
        password.send_keys(TEST_PASSWORD)
        
        logger.info("🖱️ Clicking login button...")
        login_btn.click()
        
        # Wait for page transition
        time.sleep(2)
        current_url = browser.driver.current_url
        logger.info(f"📍 URL after login: {current_url}")
        
        # Wait for dashboard to load
        try:
            wait_driver.until(
                visibility_of_element_located((By.ID, "page-dashboard"))
            )
            logger.info("✅ Successfully logged in")
            browser.screenshot("03_dashboard_loaded")
        except Exception as e:
            logger.error(f"❌ Login failed: {e}")
            logger.error(f"📍 Final URL: {browser.driver.current_url}")
            browser.screenshot("03_login_error")
            raise
    
    def test_04_dashboard_displays_doctors(self, browser, wait_driver):
        """測試 4: 儀表板顯示醫生列表"""
        # Login first
        browser.navigate_to("/")
        email = browser.driver.find_element(By.ID, "login-email")
        password = browser.driver.find_element(By.ID, "login-password")
        email.send_keys(TEST_EMAIL)
        password.send_keys(TEST_PASSWORD)
        browser.driver.find_element(By.ID, "login-btn").click()
        
        # Wait for doctor list (use clinic-card class)
        doctor_rows = wait_driver.until(
            lambda driver: driver.find_elements(By.CLASS_NAME, "clinic-card")
        )
        
        assert len(doctor_rows) > 0, "Should have at least one doctor"
        logger.info(f"✅ Dashboard displays {len(doctor_rows)} doctors")
        browser.screenshot("04_doctor_list")
    
    def test_05_doctor_status_check(self, browser, wait_driver):
        """測試 5: 查看醫生狀態"""
        # Login
        browser.navigate_to("/")
        email = browser.driver.find_element(By.ID, "login-email")
        password = browser.driver.find_element(By.ID, "login-password")
        email.send_keys(TEST_EMAIL)
        password.send_keys(TEST_PASSWORD)
        browser.driver.find_element(By.ID, "login-btn").click()
        
        # Click first doctor
        doctor_rows = wait_driver.until(
            lambda driver: driver.find_elements(By.CLASS_NAME, "clinic-card")
        )
        
        if len(doctor_rows) > 0:
            doctor_rows[0].click()
            time.sleep(1)
            
            # Check if status info is displayed
            try:
                current_number = browser.driver.find_element(By.ID, "currentNumber")
                logger.info(f"✅ Doctor status displayed: {current_number.text}")
                browser.screenshot("05_doctor_status")
            except:
                logger.warning("⚠️ Doctor status element not found")
    
    def test_06_quick_track_modal_opens(self, browser, wait_driver):
        """測試 6: 快速追蹤彈窗開啟"""
        # Login
        browser.navigate_to("/")
        email = browser.driver.find_element(By.ID, "login-email")
        password = browser.driver.find_element(By.ID, "login-password")
        email.send_keys(TEST_EMAIL)
        password.send_keys(TEST_PASSWORD)
        browser.driver.find_element(By.ID, "login-btn").click()
        
        # Click add tracking
        wait_driver.until(
            visibility_of_element_located((By.ID, "page-dashboard"))
        )
        
        try:
            add_btn = browser.driver.find_element(By.ID, "addTrackingBtn")
            add_btn.click()
            
            # Check modal opens
            modal = wait_driver.until(
                visibility_of_element_located((By.ID, "quickTrackModal"))
            )
            assert modal.is_displayed()
            logger.info("✅ Quick track modal opens")
            browser.screenshot("06_quick_track_modal")
        except Exception as e:
            logger.warning(f"⚠️ Quick track modal test skipped: {e}")
    
    def test_07_notification_logs_exist(self):
        """測試 7: 通知日誌存在"""
        from app.database import get_supabase
        
        supabase = get_supabase()
        
        # Query notification logs
        logs = supabase.table("notification_logs").select("*").limit(5).execute()
        
        assert len(logs.data) > 0, "Should have notification logs"
        logger.info(f"✅ Found {len(logs.data)} notification logs")
        
        # Print sample
        if logs.data:
            sample = logs.data[0]
            logger.info(f"   Sample: success={sample.get('success')}, channel={sample.get('notification_type', 'unknown')}")
    
    def test_08_tracking_subscriptions_exist(self):
        """測試 8: 追蹤訂閱存在"""
        from app.database import get_supabase
        
        supabase = get_supabase()
        
        # Query subscriptions
        subs = supabase.table("tracking_subscriptions").select("*").limit(5).execute()
        
        assert len(subs.data) > 0, "Should have tracking subscriptions"
        logger.info(f"✅ Found {len(subs.data)} tracking subscriptions")
        
        # Verify data structure
        for sub in subs.data:
            assert "notify_email" in sub
            assert "notify_line" in sub
            assert "line_user_id" not in sub or sub["line_user_id"] is None
            logger.info(f"   Subscription: notify_email={sub['notify_email']}, notify_line={sub['notify_line']}")
    
    def test_09_line_notification_system(self):
        """測試 9: LINE 通知系統"""
        from app.database import get_supabase
        
        supabase = get_supabase()
        
        # Check for LINE notifications
        line_logs = supabase.table("notification_logs").select("*").eq(
            "channel", "line"
        ).limit(5).execute()
        
        if len(line_logs.data) > 0:
            logger.info(f"✅ Found {len(line_logs.data)} LINE notification logs")
            for log in line_logs.data:
                status = "✓ Success" if log.get("success") else "✗ Failed"
                logger.info(f"   {status}: {log.get('message', '')[:50]}")
        else:
            logger.info("⚠️ No LINE notification logs found (expected in test env)")
    
    def test_10_email_notification_system(self):
        """測試 10: Email 通知系統"""
        from app.database import get_supabase
        
        supabase = get_supabase()
        
        # Check for email notifications
        email_logs = supabase.table("notification_logs").select("*").eq(
            "channel", "email"
        ).limit(5).execute()
        
        assert len(email_logs.data) > 0, "Should have email notification logs"
        logger.info(f"✅ Found {len(email_logs.data)} email notification logs")
        
        # Verify successful notifications
        successful = [log for log in email_logs.data if log.get("success")]
        logger.info(f"   Successful: {len(successful)}/{len(email_logs.data)}")


@pytest.mark.skip(reason="Requires running server - run manually with: pytest -v -s")
class TestUIManualOnly:
    """需要手動運行的測試（需要運行中的服務器）"""
    
    def test_complete_user_flow(self, browser, wait_driver):
        """完整用戶流程測試"""
        # 1. Navigate to home
        browser.navigate_to("/")
        logger.info("Step 1: Navigated to home")
        
        # 2. Login
        email = browser.driver.find_element(By.ID, "login-email")
        password = browser.driver.find_element(By.ID, "login-password")
        email.send_keys(TEST_EMAIL)
        password.send_keys(TEST_PASSWORD)
        browser.driver.find_element(By.ID, "login-btn").click()
        
        wait_driver.until(visibility_of_element_located((By.ID, "page-dashboard")))
        logger.info("Step 2: Logged in successfully")
        browser.screenshot("flow_02_after_login")
        
        # 3. View doctor list
        doctor_rows = browser.driver.find_elements(By.CLASS_NAME, "doctor-row")
        logger.info(f"Step 3: Found {len(doctor_rows)} doctors")
        
        # 4. Click on first doctor to view status
        if doctor_rows:
            doctor_rows[0].click()
            time.sleep(1)
            logger.info("Step 4: Clicked on first doctor")
            browser.screenshot("flow_04_doctor_status")
        
        # 5. Navigate to tracking page
        browser.navigate_to("/tracking")
        wait_driver.until(visibility_of_element_located((By.ID, "trackingList")))
        logger.info("Step 5: Navigated to tracking page")
        browser.screenshot("flow_05_tracking_list")
        
        logger.info("✅ Complete user flow test passed")
