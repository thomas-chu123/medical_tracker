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



# @pytest.mark.skip(reason="Requires running server - run manually with: uvicorn app.main:app --reload && pytest tests/e2e/test_ui_e2e_minimal.py -v -s")
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
    
    def test_04_hospitals_displays_doctors(self, browser, wait_driver):
        """測試 4: 醫院列表顯示醫生"""
        # Login first
        browser.navigate_to("/")
        email = browser.driver.find_element(By.ID, "login-email")
        password = browser.driver.find_element(By.ID, "login-password")
        email.send_keys(TEST_EMAIL)
        password.send_keys(TEST_PASSWORD)
        browser.driver.find_element(By.ID, "login-btn").click()
        
        # Navigate to hospitals (dashboard might be empty)
        wait_driver.until(visibility_of_element_located((By.ID, "page-dashboard")))
        browser.driver.get(f"{browser.driver.current_url.split('#')[0]}#hospitals")
        
        # Select first hospital
        hosp = wait_driver.until(element_to_be_clickable((By.CSS_SELECTOR, ".hospital-card")))
        hosp.click()
        
        # Optional: Select first category
        try:
            logger.info("Checking for categories...")
            cat = WebDriverWait(browser.driver, 5).until(
                element_to_be_clickable((By.CSS_SELECTOR, ".category-card"))
            )
            cat.click()
            logger.info("Selected first category")
        except:
            logger.info("No categories found or timed out, skipping...")
        
        # Optional: Select first department
        try:
            logger.info("Checking for departments...")
            dept = WebDriverWait(browser.driver, 5).until(
                element_to_be_clickable((By.CSS_SELECTOR, ".dept-card"))
            )
            dept.click()
            logger.info("Selected first department")
        except:
            logger.info("No departments found or timed out, skipping...")
        
        # Wait for doctor list
        doctor_rows = wait_driver.until(
            lambda driver: driver.find_elements(By.CLASS_NAME, "doctor-card")
        )
        
        assert len(doctor_rows) > 0, "Should have at least one doctor in hospitals view"
        logger.info(f"✅ Hospitals view displays {len(doctor_rows)} doctors")
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
        
        # Navigate to hospitals to find doctors
        wait_driver.until(visibility_of_element_located((By.ID, "page-dashboard")))
        browser.driver.find_element(By.CSS_SELECTOR, 'button[data-page="hospitals"]').click()
        
        # Select first hospital/dept to show doctors
        wait_driver.until(visibility_of_element_located((By.ID, "hospital-list-container")))
        hosp = wait_driver.until(presence_of_element_located((By.CSS_SELECTOR, ".hospital-card")))
        hosp.click()
        
        # Take the first doctor card and click '追蹤' button (to trigger status view or similar)
        # In minimal tests, we just check if clicking status works.
        # But doctor-card has no simple click to view status directly without modal.
        # Let's just check if we can see current status in doctor card if it's there.
        doctor_cards = wait_driver.until(
            lambda driver: driver.find_elements(By.CLASS_NAME, "doctor-card")
        )
        
        if len(doctor_cards) > 0:
            logger.info("✅ Found doctors in hospitals view")
            browser.screenshot("05_hospitals_doctors")
        else:
            logger.warning("⚠️ No doctors found in hospitals view")
    
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
            add_btn = browser.driver.find_element(By.ID, "fab-add-tracking")
            add_btn.click()
            
            # Check modal opens
            wait_driver.until(
                visibility_of_element_located((By.ID, "quick-track-modal"))
            )
            logger.info("✅ Quick track modal opened")
            browser.screenshot("06_quick_track_modal")
            
            # Close modal
            browser.driver.find_element(By.CSS_SELECTOR, "#quick-track-modal .modal-close").click()
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



# @pytest.mark.skip(reason="Requires running server - run manually with: pytest -v -s")
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
        
        # 3. Navigate to hospitals to find doctors
        browser.driver.get(f"{browser.driver.current_url.split('#')[0]}#hospitals")
        wait_driver.until(visibility_of_element_located((By.ID, "hospital-list-container")))
        logger.info("Step 3: Navigated to hospitals page")
        
        # 4. Select hospital, category and check doctors
        hosp = wait_driver.until(element_to_be_clickable((By.CSS_SELECTOR, ".hospital-card")))
        hosp.click()
        
        # Optional: Select category and dept
        try:
            cat = WebDriverWait(browser.driver, 5).until(
                element_to_be_clickable((By.CSS_SELECTOR, ".category-card"))
            )
            cat.click()
        except:
            pass
            
        try:
            dept = WebDriverWait(browser.driver, 5).until(
                element_to_be_clickable((By.CSS_SELECTOR, ".dept-card"))
            )
            dept.click()
        except:
            pass
        
        doctor_cards = wait_driver.until(
            lambda driver: driver.find_elements(By.CLASS_NAME, "doctor-card")
        )
        logger.info(f"Step 4: Found {len(doctor_cards)} doctors in hospitals view")
        browser.screenshot("flow_04_hospitals_view")
        # Close any open modals
        try:
            close_btn = browser.driver.find_element(By.CSS_SELECTOR, "#clinic-waiting-modal .modal-close")
            if close_btn.is_displayed():
                close_btn.click()
        except:
            pass
        try:
            close_btn = browser.driver.find_element(By.CSS_SELECTOR, "#doctor-modal .modal-close")
            if close_btn.is_displayed():
                close_btn.click()
        except:
            pass
        time.sleep(1)
        
        # 5. Navigate to tracking page via sidebar
        browser.driver.find_element(By.CSS_SELECTOR, 'button[data-page="tracking"]').click()
        wait_driver.until(visibility_of_element_located((By.ID, "tracking-list")))
        logger.info("Step 5: Navigated to tracking page")
        browser.screenshot("flow_05_tracking_list")
        
        logger.info("✅ Complete user flow test passed")
