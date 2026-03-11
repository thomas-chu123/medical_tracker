"""
Page Object Model for Medical Tracking Application.

Encapsulates UI interactions for maintainability and reusability.
"""
from selenium.webdriver.common.by import By
from selenium.webdriver.support.expected_conditions import (
    presence_of_element_located,
    presence_of_all_elements_located,
    visibility_of_element_located,
    invisibility_of_element_located,
    alert_is_present,
)
import time
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
    STATS_TOTAL = (By.ID, "stats-total-region")
    DOCTOR_LIST = (By.ID, "dashboard-tracking-grid")
    NAV_HOSPITALS = (By.CSS_SELECTOR, "button[data-page='hospitals']")
    NAV_TRACKING = (By.CSS_SELECTOR, "button[data-page='tracking']")
    NAV_ADD_TRACKING = (By.CSS_SELECTOR, "button[data-page='add-tracking']")
    ADD_TRACKING_BUTTON = (By.ID, "submit-tracking-btn")
    REFRESH_BUTTON = (By.XPATH, "//button[contains(., '重新整理')]")
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
    
    def get_doctor_list(self, wait=True) -> list:
        """取得醫生列表"""
        if wait:
            try:
                # Wait for at least one card to appear
                self.wait.until(presence_of_element_located(self.DOCTOR_ROW))
            except:
                logger.warning("No doctors appeared on dashboard within timeout")
        
        rows = self.driver.find_elements(*self.DOCTOR_ROW)
        logger.info(f"Found {len(rows)} doctors on dashboard")
        return rows
    
    def click_add_tracking(self):
        """點擊導航欄的新增追蹤按鈕"""
        logger.info("Clicking nav add tracking button")
        button = self.wait.until(presence_of_element_located(self.NAV_ADD_TRACKING))
        self.driver.execute_script("arguments[0].click();", button)

    def click_hospitals(self):
        """點擊導航欄的找醫院按鈕"""
        logger.info("Clicking nav hospitals button")
        button = self.wait.until(presence_of_element_located(self.NAV_HOSPITALS))
        self.driver.execute_script("arguments[0].click();", button)
    
    def click_refresh(self):
        """點擊重新整理按鈕"""
        logger.info("Clicking dash refresh button")
        btn = self.wait.until(presence_of_element_located(self.REFRESH_BUTTON))
        self.driver.execute_script("arguments[0].click();", btn)
    
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
    SUBMIT_BUTTON = (By.XPATH, "//button[contains(., '確認追蹤')]")
    CLOSE_BUTTON = (By.CLASS_NAME, "modal-close")
    SUCCESS_MESSAGE = (By.CSS_SELECTOR, ".toast.success")
    ERROR_MESSAGE = (By.CSS_SELECTOR, ".toast.error")
    
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
        # Wait until options are loaded
        self.wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, "#qt-date option")) > 1)
        
        option = self.driver.find_element(By.CSS_SELECTOR, f"option[value='{date_value}']")
        option.click()
        
    def select_first_available_date(self) -> str:
        """選擇第一個可用的日期，並返回日期字串"""
        logger.info("Selecting first available date")
        self.wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, "#qt-date option")) > 1)
        
        date_select = self.wait.until(visibility_of_element_located(self.DATE_SELECT))
        options = date_select.find_elements(By.TAG_NAME, "option")
        for opt in options:
            val = opt.get_attribute("value")
            if val:
                logger.info(f"Setting qt-date value to: {val}")
                self.driver.execute_script(f"arguments[0].value = '{val}'; arguments[0].onchange();", date_select)
                time.sleep(1)
                return val
        return ""
    
    def set_session(self, session_value: str):
        """設定診次"""
        logger.info(f"Setting session: {session_value}")
        session_select = self.wait.until(visibility_of_element_located(self.SESSION_SELECT))
        # Wait until options are loaded
        self.wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, "#qt-session option")) > 0)
        
        self.driver.execute_script(f"arguments[0].value = '{session_value}'; if(arguments[0].onchange) arguments[0].onchange();", session_select)
        time.sleep(0.5)
        
    def select_first_available_session(self) -> str:
        """選擇第一個可用的診次，並返回診次字串"""
        logger.info("Selecting first available session")
        # Wait until options are loaded (after date change)
        self.wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, "#qt-session option")) > 0)
        
        session_select = self.wait.until(visibility_of_element_located(self.SESSION_SELECT))
        options = session_select.find_elements(By.TAG_NAME, "option")
        for opt in options:
            val = opt.get_attribute("value")
            if val:
                logger.info(f"Setting qt-session value to: {val}")
                self.driver.execute_script(f"arguments[0].value = '{val}'; if(arguments[0].onchange) arguments[0].onchange();", session_select)
                time.sleep(0.5)
                return val
        return ""
    
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
            msg = self.wait.until(visibility_of_element_located(self.SUCCESS_MESSAGE))
            return msg.text
        except:
            return ""

class TrackingStepperPage:
    """新增追蹤流程頁面"""
    
    def __init__(self, driver, wait):
        self.driver = driver
        self.wait = wait
        
    STEPPER_CONTAINER = (By.ID, "page-add-tracking")
    HOSPITAL_GRID = (By.ID, "step1-hospital-grid")
    DEPT_GRID = (By.ID, "step2-dept-grid")
    DOCTOR_GRID = (By.ID, "step3-doctor-grid")
    
    DATE_SELECT = (By.ID, "modal-date")
    SESSION_SELECT = (By.ID, "modal-session")
    APPOINTMENT_NUMBER = (By.ID, "modal-appointment-number")
    
    NOTIFY_20 = (By.ID, "notify-20")
    NOTIFY_10 = (By.ID, "notify-10")
    NOTIFY_5 = (By.ID, "notify-5")
    NOTIFY_EMAIL = (By.ID, "notify-email")
    NOTIFY_LINE = (By.ID, "notify-line")
    
    NEXT_BUTTON_STEP4 = (By.XPATH, "//div[@id='step-4-content']//button[contains(text(), '下一步')]")
    SUBMIT_BUTTON = (By.ID, "submit-tracking-btn")
    SUCCESS_MESSAGE = (By.CSS_SELECTOR, ".toast.success")
    
    def is_open(self) -> bool:
        """檢查是否開啟且可見"""
        try:
            elem = self.wait.until(visibility_of_element_located(self.STEPPER_CONTAINER))
            # Also wait for hospital buttons to load
            self.wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, "#step1-hospital-grid button")) > 0)
            return elem.is_displayed()
        except:
            return False
            
    def select_first_hospital(self):
        """選擇第一家醫院"""
        grid = self.wait.until(visibility_of_element_located(self.HOSPITAL_GRID))
        btns = grid.find_elements(By.TAG_NAME, "button")
        if btns:
            self.driver.execute_script("arguments[0].click();", btns[0])
            
    def select_first_department(self):
        """選擇第一個科別 - assuming the grid loads"""
        # wait a bit for grid to populate
        self.wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, "#step2-dept-grid button")) > 0)
        grid = self.driver.find_element(*self.DEPT_GRID)
        btns = grid.find_elements(By.TAG_NAME, "button")
        if btns:
            self.driver.execute_script("arguments[0].click();", btns[0])
            time.sleep(0.5)
            
    def select_first_doctor(self):
        """選擇第一位醫生"""
        self.wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, "#step3-doctor-grid .clinic-card")) > 0)
        grid = self.driver.find_element(*self.DOCTOR_GRID)
        cards = grid.find_elements(By.CLASS_NAME, "clinic-card")
        if cards:
            self.driver.execute_script("arguments[0].click();", cards[0])
            time.sleep(0.5)
            
    def fill_step4(self, date_val: str, session_val: str, appt_num: int = None, 
                   notify_20=True, notify_10=True, notify_5=True,
                   notify_email=True, notify_line=False):
        """填寫日期等資料"""
        self.wait.until(visibility_of_element_located(self.DATE_SELECT))
        # Select date
        date_sel = self.driver.find_element(*self.DATE_SELECT)
        self.driver.execute_script(f"arguments[0].value = '{date_val}'; arguments[0].dispatchEvent(new Event('change'));", date_sel)
        # Select session
        sess_sel = self.driver.find_element(*self.SESSION_SELECT)
        self.driver.execute_script(f"arguments[0].value = '{session_val}'; arguments[0].dispatchEvent(new Event('change'));", sess_sel)
        
        if appt_num:
            appt_input = self.driver.find_element(*self.APPOINTMENT_NUMBER)
            appt_input.clear()
            appt_input.send_keys(str(appt_num))
            
        def set_chk(locator, value):
            chk = self.driver.find_element(*locator)
            if chk.is_selected() != value:
                self.driver.execute_script("arguments[0].click();", chk)
                
        set_chk(self.NOTIFY_20, notify_20)
        set_chk(self.NOTIFY_10, notify_10)
        set_chk(self.NOTIFY_5, notify_5)
        set_chk(self.NOTIFY_EMAIL, notify_email)
        set_chk(self.NOTIFY_LINE, notify_line)
        
        # Click next
        next_btn = self.driver.find_element(*self.NEXT_BUTTON_STEP4)
        self.driver.execute_script("arguments[0].click();", next_btn)
        
    def submit_step5(self):
        self.wait.until(visibility_of_element_located(self.SUBMIT_BUTTON))
        btn = self.driver.find_element(*self.SUBMIT_BUTTON)
        self.driver.execute_script("arguments[0].click();", btn)
        
    def get_success_message(self) -> str:
        try:
            msg = self.wait.until(visibility_of_element_located(self.SUCCESS_MESSAGE))
            return msg.text
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
    DELETE_BUTTON = (By.CSS_SELECTOR, "button.btn-danger, .delete-tracking-btn")
    EDIT_BUTTON = (By.CLASS_NAME, "edit-tracking-btn")
    DOCTOR_NAME = (By.CSS_SELECTOR, ".tc-header .doctor-name, .tracking-doctor-name")
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
        """刪除追蹤並等待消失"""
        logger.info(f"Deleting tracking for: {doctor_name}")
        item = self.find_tracking_by_doctor(doctor_name)
        if item:
            # Get common identifier to wait for removal
            delete_btn = item.find_element(*self.DELETE_BUTTON)
            self.driver.execute_script("arguments[0].click();", delete_btn)
            
            # 處理瀏覽器原生確認視窗
            try:
                self.wait.until(alert_is_present())
                alert = self.driver.switch_to.alert
                alert.accept()
                
                # Wait for the specific card to be removed from DOM
                self.wait.until(invisibility_of_element_located(item))
                logger.info(f"✅ Item for {doctor_name} removed from UI")
                return True
            except Exception as e:
                logger.warning(f"⚠️ Error during alert/removal wait: {e}")
                time.sleep(1) # Fallback
            return True
        return False


class DoctorStatusPage:
    """醫生狀態檢查頁面"""
    
    def __init__(self, driver, wait):
        self.driver = driver
        self.wait = wait
    
    # Locators
    STATUS_CONTAINER = (By.ID, "doctor-modal")
    DOCTOR_NAME = (By.ID, "doctor-modal-title")
    CLOSE_BUTTON = (By.XPATH, "//div[@id='doctor-modal']//button[contains(@class, 'btn-outline')]")
    FIRST_ROW_CURRENT_NUMBER = (By.XPATH, "//div[@id='doctor-modal-body']//tbody/tr[1]/td[5]")
    FIRST_ROW_TOTAL_QUOTA = (By.XPATH, "//div[@id='doctor-modal-body']//tbody/tr[1]/td[3]")
    
    def is_loaded(self) -> bool:
        """檢查狀態頁面是否載入"""
        try:
            self.wait.until(visibility_of_element_located(self.STATUS_CONTAINER))
            # Wait for spinner to disappear
            self.wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, "#doctor-modal-body .spinner")) == 0)
            return True
        except:
            return False
    
    def get_doctor_name(self) -> str:
        """取得醫生名稱"""
        elem = self.driver.find_element(*self.DOCTOR_NAME)
        return elem.text
    
    def get_current_number(self):
        """取得當前號碼"""
        elem = self.driver.find_element(*self.FIRST_ROW_CURRENT_NUMBER)
        try:
            return int(elem.text)
        except ValueError:
            return -1 # '—' or empty
    
    def get_total_quota(self):
        """取得總額度"""
        elem = self.driver.find_element(*self.FIRST_ROW_TOTAL_QUOTA)
        try:
            return int(elem.text)
        except ValueError:
            return -1 # '—'
    
    def close(self):
        """關閉彈窗"""
        try:
            btn = self.driver.find_element(*self.CLOSE_BUTTON)
            btn.click()
            time.sleep(0.5)
        except:
            pass

class HospitalsPage:
    """醫院列表與找醫生頁面"""
    
    def __init__(self, driver, wait):
        self.driver = driver
        self.wait = wait
        
    CONTAINER = (By.ID, "page-hospitals")
    DOCTOR_GRID = (By.ID, "doctors-grid")
    DOCTOR_CARD = (By.CSS_SELECTOR, "#doctors-grid .card")
    
    # Combobox locators
    COMBO_ARROW = (By.CSS_SELECTOR, "#cb-hospital .combo-arrow")
    COMBO_OPTS = (By.CSS_SELECTOR, "#cb-hospital-list .combo-opt")
    
    CAT_BTNS = (By.CSS_SELECTOR, "#hs-category-chips .cat-chip")
    DEPT_BTNS = (By.CSS_SELECTOR, "#hs-dept-grid button")
    
    def is_loaded(self) -> bool:
        """檢查頁面是否載入"""
        try:
            self.wait.until(visibility_of_element_located(self.CONTAINER))
            return True
        except:
            return False
            
    def select_first_hospital(self):
        """選擇第一個醫院 (透過 Combobox)"""
        logger.info("Selecting first hospital via combobox")
        arrow = self.wait.until(presence_of_element_located(self.COMBO_ARROW))
        arrow.click()
        time.sleep(0.5)
        
        btns = self.wait.until(presence_of_all_elements_located(self.COMBO_OPTS))
        if btns:
            btns[0].click()
            time.sleep(1)
            
    def select_first_category(self):
        """選擇第一個科室類別"""
        logger.info("Selecting first category")
        btns = self.wait.until(presence_of_all_elements_located(self.CAT_BTNS))
        if btns:
            btns[0].click()
            time.sleep(1)
            
    def select_first_dept(self):
        """選擇第一個科室"""
        btns = self.wait.until(presence_of_all_elements_located(self.DEPT_BTNS))
        if btns:
            btns[0].click()
            time.sleep(1)
            
    def get_doctor_cards(self) -> list:
        """取得醫生卡片列表"""
        # Wait for potential spinner or empty state to clear
        time.sleep(1)
        cards = self.driver.find_elements(*self.DOCTOR_CARD)
        logger.info(f"Found {len(cards)} doctor cards in hospital view")
        return cards
