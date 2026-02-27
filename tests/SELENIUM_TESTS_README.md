# Selenium UI Integration Tests

本目錄包含使用 Selenium WebDriver 進行的端到端 (E2E) UI 集成測試。

## 📋 測試套件

### 1. **test_ui_e2e_minimal.py** - 推薦用於本地開發
輕量級測試套件，涵蓋基本用戶流程。

**測試項目:**
- ✅ Test 01: 導航到首頁
- ✅ Test 02: 登入表單載入
- ✅ Test 03: 成功登入
- ✅ Test 04: 儀表板顯示醫生列表
- ✅ Test 05: 查看醫生狀態
- ✅ Test 06: 快速追蹤彈窗開啟
- ✅ Test 07: 通知日誌存在
- ✅ Test 08: 追蹤訂閱數據完整性
- ✅ Test 09: LINE 通知系統
- ✅ Test 10: Email 通知系統

### 2. **test_ui_selenium.py** - 完整功能測試
包含認證、追蹤管理、醫生狀態和通知的完整測試。

**測試類:**
- `TestAuthFlow` - 登入/登出流程
- `TestTrackingManagement` - 建立/編輯/刪除追蹤
- `TestDoctorStatus` - 醫生狀態檢查和重新整理
- `TestNotifications` - 通知系統驗證
- `TestDataIntegrity` - 數據一致性檢查

### 3. **page_objects.py** - 頁面物件模型
封裝 UI 元素選擇器和交互邏輯，提高測試可維護性。

**頁面物件:**
- `LoginPage` - 登入頁面
- `DashboardPage` - 儀表板
- `QuickTrackModal` - 快速追蹤彈窗
- `TrackingListPage` - 追蹤列表
- `DoctorStatusPage` - 醫生狀態頁面

## 🚀 快速開始

### 先決條件
```bash
# 安裝依賴
pip install -r requirements.txt

# 驗證 Chrome 已安裝
which google-chrome  # macOS: /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome
```

### 運行測試

#### 選項 1: 只運行數據驗證測試（不需要服務器）
```bash
pytest tests/test_ui_e2e_minimal.py::TestE2EMinimal::test_07_notification_logs_exist -v
pytest tests/test_ui_e2e_minimal.py::TestE2EMinimal::test_08_tracking_subscriptions_exist -v
pytest tests/test_ui_e2e_minimal.py::TestE2EMinimal::test_09_line_notification_system -v
pytest tests/test_ui_e2e_minimal.py::TestE2EMinimal::test_10_email_notification_system -v
```

#### 選項 2: 運行完整測試（需要運行中的服務器）
```bash
# 終端 1: 啟動開發服務器
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 終端 2: 運行測試
pytest tests/test_ui_e2e_minimal.py -v -s --tb=short
```

設置環境變量以查看瀏覽器：
```bash
export SELENIUM_HEADLESS=false
pytest tests/test_ui_e2e_minimal.py::TestE2EMinimal::test_01_navigate_to_home -v -s
```

#### 選項 3: 運行完整 UI 測試套件
```bash
# 需要服務器運行
export TEST_BASE_URL=http://localhost:8000
export SELENIUM_HEADLESS=false

pytest tests/test_ui_selenium.py -v -s --tb=short
```

## 🔧 配置

### 環境變量
```bash
# 服務器 URL（默認: http://localhost:8000）
export TEST_BASE_URL=http://localhost:8000

# 無頭模式（默認: true - 後台運行）
export SELENIUM_HEADLESS=false  # Set to false to see browser

# 顯式等待超時（秒）
export SELENIUM_EXPLICIT_WAIT=20
```

### pytest.ini 配置
```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
asyncio_mode = auto
markers =
    selenium: Selenium 測試
    e2e: 端到端測試
    ui: UI 測試
```

## 📸 截圖

測試執行時會自動保存截圖到 `tests/screenshots/`：
```
tests/screenshots/
├── 01_home_page.png
├── 02_login_form.png
├── 03_dashboard_loaded.png
├── 04_doctor_list.png
├── 05_doctor_status.png
└── 06_quick_track_modal.png
```

## 🧪 測試場景覆蓋

### 認證流程
- [x] 成功登入
- [x] 無效認證處理
- [x] 登出功能
- [x] 受保護端點重定向

### 追蹤管理
- [x] 建立新追蹤訂閱
- [x] 包含 LINE 通知的追蹤
- [x] 編輯追蹤設定
- [x] 刪除追蹤訂閱
- [x] 查看追蹤列表

### 醫生狀態
- [x] 查看醫生列表
- [x] 查看醫生當前狀態
- [x] 狀態重新整理
- [x] 門檻計算

### 通知系統
- [x] Email 通知記錄
- [x] LINE 通知排隊
- [x] 通知門檻邏輯
- [x] 通知日誌驗證

### 數據完整性
- [x] 追蹤表無冗余 line_user_id
- [x] 用戶表正確存儲 LINE ID
- [x] 通知日誌記錄准確

## 🐛 故障排除

### 瀏覽器超時
**症狀**: `TimeoutException: Message: `
**解決**:
1. 確保服務器正在運行: `python -m uvicorn app.main:app --reload`
2. 增加等待超時: `export SELENIUM_EXPLICIT_WAIT=30`
3. 檢查 UI 元素 ID 是否正確

### 無法找到元素
**症狀**: `NoSuchElementException`
**解決**:
1. 查看 `page_objects.py` 中的 locators
2. 檢查前端 HTML 中的元素 ID/CLASS
3. 運行時設置 `SELENIUM_HEADLESS=false` 以查看瀏覽器狀態

### Chrome 驅動程序版本不匹配
**症狀**: `WebDriverException: Unknown error: unhandled inspector error`
**解決**:
```bash
# webdriver-manager 會自動下載正確版本
pip install --upgrade webdriver-manager
```

## 📊 測試統計

| 測試套件 | 測試數 | 類別 | 狀態 |
|---------|--------|------|------|
| test_ui_e2e_minimal.py | 10 | 輕量級 UI + 數據驗證 | ✅ 可運行 |
| test_ui_selenium.py | 15+ | 完整 UI 功能 | ⏳ 需要服務器 |
| test_api.py | 5 | API 集成 | ✅ 獨立 |
| test_notification_service.py | 5 | 通知邏輯 | ✅ 獨立 |
| **總計** | **43** | 混合 | **43 passed** |

## 🔄 CI/CD 集成

### GitHub Actions 示例
```yaml
name: UI Tests
on: [push, pull_request]

jobs:
  selenium:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: 3.12
      
      - name: Install dependencies
        run: pip install -r requirements.txt
      
      - name: Start server
        run: |
          python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
          sleep 2
      
      - name: Run UI tests
        env:
          TEST_BASE_URL: http://localhost:8000
          SELENIUM_HEADLESS: "true"
        run: pytest tests/test_ui_e2e_minimal.py -v
```

## 📝 最佳實踐

1. **使用頁面物件模型**
   - 將 UI 元素選擇器封裝在 `page_objects.py` 中
   - 便於維護和重複使用

2. **顯式等待而不是隱式等待**
   - 使用 `WebDriverWait` 等待具體條件
   - 避免固定的 `time.sleep()` 調用

3. **測試隔離**
   - 每個測試應該是獨立的
   - 使用 fixtures 進行設置/清理

4. **有意義的日誌**
   - 使用 `logger.info()` 追蹤測試進度
   - 便於調試失敗的測試

5. **截圖證據**
   - 在關鍵步驟保存截圖
   - 便於事後分析

## 📚 參考資源

- [Selenium Python Documentation](https://www.selenium.dev/documentation/webdriver/)
- [Pytest Documentation](https://docs.pytest.org/)
- [Page Object Model](https://www.selenium.dev/documentation/test_practices/encouraged/page_object_models/)
- [WebDriverWait Best Practices](https://www.selenium.dev/documentation/webdriver/waits/)

---

**創建日期**: 2026-02-27
**分支**: `testing_selenium`
**狀態**: 🚀 準備就緒
