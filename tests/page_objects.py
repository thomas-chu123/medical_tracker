"""
Page Object Model for Medical Tracking Application.

Encapsulates UI interactions for maintainability and reusability.
"""
from selenium.webdriver.common.by import By
from selenium.webdriver.support.expected_conditions import (
    presence_of_element_located,
    visibility_of_element_located,
    invisibility_of_element_located,
)
import logging


logger = logging.getLogger(__name__)


class LoginPage:
    """登入頁面物件"""
    
    def __init__(self, driver, wait):
        self.driver = driver
        self.wait = wait
    
    # Locators
    EMAIL_INPUT = (By.ID, "login-email")
    PASSWORD_INPUT = (By.ID, "login-password")
    LOGIN_BUTTON = (By.ID, "login-btn")
    ERROR_MESSAGE = (By.CLASS_NAME, "error-message")
    
    def enter_email(self, email: str):
        """輸入 email"""
        logger.info(f"Entering email: {email}")
        element = self.wait.until(visibility_of_element_located(self.EMAIL_INPUT))
        element.clear()
        element.send_keys(email)
    
    def enter_password(self, password: str):
        """輸入密碼"""
        logger.info("Entering password")
        element = self.wait.until(visibility_of_element_located(self.PASSWORD_INPUT))
        element.clear()
        element.send_keys(password)
    
    def click_login(self):
        """點擊登入按鈕"""
        logger.info("Clicking login button")
        button = self.wait.until(visibility_of_element_located(self.LOGIN_BUTTON))
        button.click()
    
    def get_error_message(self) -> str:
        """取得錯誤訊息"""
        try:
            error = self.wait.until(visibility_of_element_located(self.ERROR_MESSAGE))
            return error.text
        except:
            return ""
    
    def is_error_shown(self) -> bool:
        """檢查是否顯示錯誤"""
        try:
            self.wait.until(visibility_of_element_located(self.ERROR_MESSAGE))
            return True
        except:
            return False


class DashboardPage:
    """儀表板頁面物件"""
    
    def __init__(self, driver, wait):
        self.driver = driver
        self.wait = wait
    
    # Locators
    DASHBOARD_CONTAINER = (By.ID, "page-dashboard")
    STATS_TOTAL = (By.ID, "statsTotalRegion")
    DOCTOR_LIST = (By.ID, "doctorList")
    ADD_TRACKING_BUTTON = (By.ID, "submit-tracking-btn")
    LOGOUT_BUTTON = (By.ID, "btn-logout")
    DOCTOR_ROW = (By.CLASS_NAME, "clinic-card")
    
    def is_loaded(self) -> bool:
        """檢查儀表板是否載入"""
        try:
            self.wait.until(visibility_of_element_located(self.DASHBOARD_CONTAINER))
            logger.info("Dashboard loaded successfully")
            return True
        except:
            logger.error("Dashboard failed to load")
            return False
    
    def get_doctor_list(self) -> list:
        """取得醫生列表"""
        rows = self.driver.find_elements(*self.DOCTOR_ROW)
        logger.info(f"Found {len(rows)} doctors on dashboard")
        return rows
    
    def click_add_tracking(self):
        """點擊新增追蹤按鈕"""
        logger.info("Clicking add tracking button")
        button = self.wait.until(visibility_of_element_located(self.ADD_TRACKING_BUTTON))
        button.click()
    
    def get_doctor_by_name(self, doctor_name: str):
        """根據醫生名稱尋找"""
        doctors = self.get_doctor_list()
        for doctor in doctors:
            name_elem = doctor.find_element(By.CLASS_NAME, "doctor-name")
            if doctor_name in name_elem.text:
                return doctor
        return None


class QuickTrackModal:
    """快速追蹤彈窗"""
    
    def __init__(self, driver, wait):
        self.driver = driver
        self.wait = wait
    
    # Locators
    MODAL = (By.ID, "quick-track-modal")
    DOCTOR_SELECT = (By.ID, "qt-doctor-name")
    DATE_SELECT = (By.ID, "qt-date")
    SESSION_SELECT = (By.ID, "qt-session")
    THRESHOLD_20 = (By.ID, "qt-notify-20")
    THRESHOLD_10 = (By.ID, "qt-notify-10")
    THRESHOLD_5 = (By.ID, "qt-notify-5")
    NOTIFY_EMAIL = (By.ID, "qt-notify-email")
    NOTIFY_LINE = (By.ID, "qt-notify-line")
    APPOINTMENT_NUMBER = (By.ID, "qt-appointment-number")
    SUBMIT_BUTTON = (By.XPATH, "//button[contains(text(), '確認追蹤')]")
    CLOSE_BUTTON = (By.CLASS_NAME, "modal-close")
    SUCCESS_MESSAGE = (By.CLASS_NAME, "success-message")
    ERROR_MESSAGE = (By.CLASS_NAME, "error-message")
    
    def is_open(self) -> bool:
        """檢查彈窗是否開啟"""
        try:
            modal = self.wait.until(visibility_of_element_located(self.MODAL))
            return "open" in modal.get_attribute("class") or modal.is_displayed()
        except:
            return False
    
    def select_doctor(self, doctor_id: str):
        """選擇醫生"""
        logger.info(f"Selecting doctor: {doctor_id}")
        # 實際上是通過點擊診生卡來選擇
        doctor_elem = self.driver.find_element(By.XPATH, f"//div[@class='clinic-card'][contains(., '{doctor_id}')]")
        doctor_elem.click()
    
    def set_date(self, date_value: str):
        """設定就診日期"""
        logger.info(f"Setting appointment date: {date_value}")
        date_select = self.wait.until(visibility_of_element_located(self.DATE_SELECT))
        date_select.click()
        option = self.driver.find_element(By.CSS_SELECTOR, f"option[value='{date_value}']")
        option.click()
    
    def set_session(self, session_value: str):
        """設定診次"""
        logger.info(f"Setting session: {session_value}")
        session_select = self.wait.until(visibility_of_element_located(self.SESSION_SELECT))
        session_select.click()
        option = self.driver.find_element(By.CSS_SELECTOR, f"option[value='{session_value}']")
        option.click()
    
    def set_appointment_number(self, number: int):
        """設定號碼"""
        logger.info(f"Setting appointment number: {number}")
        input_elem = self.wait.until(visibility_of_element_located(self.APPOINTMENT_NUMBER))
        input_elem.clear()
        input_elem.send_keys(str(number))
    
    def set_thresholds(self, notify_20: bool = True, notify_10: bool = True, notify_5: bool = True):
        """設定門檻"""
        logger.info(f"Setting thresholds: 20={notify_20}, 10={notify_10}, 5={notify_5}")
        self._set_checkbox(self.THRESHOLD_20, notify_20)
        self._set_checkbox(self.THRESHOLD_10, notify_10)
        self._set_checkbox(self.THRESHOLD_5, notify_5)
    
    def set_notifications(self, email: bool = True, line: bool = False):
        """設定通知管道"""
        logger.info(f"Setting notifications: email={email}, line={line}")
        self._set_checkbox(self.NOTIFY_EMAIL, email)
        self._set_checkbox(self.NOTIFY_LINE, line)
    
    def _set_checkbox(self, locator, should_check: bool):
        """設定 checkbox 狀態"""
        checkbox = self.wait.until(visibility_of_element_located(locator))
        is_checked = checkbox.is_selected()
        if should_check and not is_checked:
            checkbox.click()
        elif not should_check and is_checked:
            checkbox.click()
    
    def submit(self):
        """提交表單"""
        logger.info("Submitting tracking form")
        button = self.wait.until(visibility_of_element_located(self.SUBMIT_BUTTON))
        button.click()
    
    def close(self):
        """關閉彈窗"""
        logger.info("Closing modal")
        button = self.wait.until(visibility_of_element_located(self.CLOSE_BUTTON))
        button.click()
    
    def get_success_message(self) -> str:
        """取得成功訊息"""
        try:
            elem = self.wait.until(visibility_of_element_located(self.SUCCESS_MESSAGE))
            return elem.text
        except:
            return ""
    
    def get_error_message(self) -> str:
        """取得錯誤訊息"""
        try:
            elem = self.wait.until(visibility_of_element_located(self.ERROR_MESSAGE))
            return elem.text
        except:
            return ""


class TrackingListPage:
    """追蹤列表頁面"""
    
    def __init__(self, driver, wait):
        self.driver = driver
        self.wait = wait
    
    # Locators
    TRACKING_LIST = (By.ID, "tracking-list")
    TRACKING_ITEM = (By.CLASS_NAME, "tracking-card")
    DELETE_BUTTON = (By.CLASS_NAME, "delete-tracking-btn")
    EDIT_BUTTON = (By.CLASS_NAME, "edit-tracking-btn")
    DOCTOR_NAME = (By.CLASS_NAME, "tracking-doctor-name")
    CONFIRM_DELETE = (By.ID, "confirmDeleteBtn")
    CANCEL_DELETE = (By.ID, "cancelDeleteBtn")
    
    def is_loaded(self) -> bool:
        """檢查列表是否載入"""
        try:
            self.wait.until(visibility_of_element_located(self.TRACKING_LIST))
            return True
        except:
            return False
    
    def get_tracking_items(self) -> list:
        """取得追蹤項目列表"""
        items = self.driver.find_elements(*self.TRACKING_ITEM)
        logger.info(f"Found {len(items)} tracking items")
        return items
    
    def find_tracking_by_doctor(self, doctor_name: str):
        """根據醫生名稱尋找追蹤"""
        items = self.get_tracking_items()
        for item in items:
            try:
                name_elem = item.find_element(*self.DOCTOR_NAME)
                if doctor_name in name_elem.text:
                    return item
            except:
                continue
        return None
    
    def delete_tracking(self, doctor_name: str):
        """刪除追蹤"""
        logger.info(f"Deleting tracking for: {doctor_name}")
        item = self.find_tracking_by_doctor(doctor_name)
        if item:
            delete_btn = item.find_element(*self.DELETE_BUTTON)
            delete_btn.click()
            # 確認刪除
            confirm_btn = self.wait.until(visibility_of_element_located(self.CONFIRM_DELETE))
            confirm_btn.click()
            return True
        return False


class DoctorStatusPage:
    """醫生狀態檢查頁面"""
    
    def __init__(self, driver, wait):
        self.driver = driver
        self.wait = wait
    
    # Locators
    STATUS_CONTAINER = (By.ID, "doctorStatus")
    DOCTOR_NAME = (By.ID, "statusDoctorName")
    CURRENT_NUMBER = (By.ID, "currentNumber")
    TOTAL_QUOTA = (By.ID, "totalQuota")
    REMAINING = (By.ID, "remaining")
    STATUS_TEXT = (By.ID, "statusText")
    REFRESH_BUTTON = (By.ID, "refreshStatusBtn")
    
    def is_loaded(self) -> bool:
        """檢查狀態頁面是否載入"""
        try:
            self.wait.until(visibility_of_element_located(self.STATUS_CONTAINER))
            return True
        except:
            return False
    
    def get_doctor_name(self) -> str:
        """取得醫生名稱"""
        elem = self.driver.find_element(*self.DOCTOR_NAME)
        return elem.text
    
    def get_current_number(self) -> int:
        """取得當前號碼"""
        elem = self.driver.find_element(*self.CURRENT_NUMBER)
        return int(elem.text)
    
    def get_total_quota(self) -> int:
        """取得總額度"""
        elem = self.driver.find_element(*self.TOTAL_QUOTA)
        return int(elem.text)
    
    def get_remaining(self) -> int:
        """取得剩餘人數"""
        elem = self.driver.find_element(*self.REMAINING)
        return int(elem.text)
    
    def get_status_text(self) -> str:
        """取得狀態文字"""
        elem = self.driver.find_element(*self.STATUS_TEXT)
        return elem.text
    
    def click_refresh(self):
        """點擊重新整理"""
        logger.info("Clicking refresh button")
        button = self.wait.until(visibility_of_element_located(self.REFRESH_BUTTON))
        button.click()
