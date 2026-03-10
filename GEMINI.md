# GEMINI.md

本文件為「台灣醫療門診追蹤系統」專案提供 Gemini 使用的脈絡與操作規範。

---

## ⚠️ 重要語言指示

**所有回覆都必須使用繁體中文 (Traditional Chinese)**

- ✅ **溝通語言**: 所有對話、回覆、程式碼註解、Code review 評論、文件說明 (`/docs`) 皆使用**繁體中文**。
- ✅ **Git 提交訊息**: 依照專案慣例，使用**英文**。
- ✅ **Pull Request 描述**: 依照專案慣例，使用**英文**。

---

## 專案概觀

本專案為「台灣醫療門診追蹤系統」，一個以 Python 開發的 Web 應用程式。系統會定時（每 3 分鐘）自動爬取合作醫院的門診叫號進度，並在使用者追蹤的門診號碼即將到達時，透過 Email 或 LINE 發送即時通知。

## 技術堆疊

- **後端**: FastAPI, Uvicorn (ASGI 伺服器)
- **資料庫**: Supabase (PostgreSQL)，透過 `supabase-py` 套件進行操作。
- **排程**: APScheduler
- **網頁爬蟲**: HTTPX, BeautifulSoup4, Selectolax
- **身分驗證**: 自訂 JWT 機制，使用 `python-jose` 進行權杖管理，`passlib` 與 `bcrypt` 進行密碼雜湊。使用者資料儲存於自訂的 `users_local` 資料表，**並非**使用 Supabase 內建的 Auth 系統。
- **通知服務**: `aiosmtplib` (非同步郵件), LINE Messaging API
- **資料驗證**: Pydantic, Pydantic-Settings
- **非同步處理**: `asyncio`, `aiofiles`
- **其他**: `python-dotenv`, `tenacity` (重試機制), `python-multipart` (表單處理)
- **前端**: 一個以 HTML/CSS/JavaScript 建構的簡單靜態前端，由 `/static` 目錄提供服務。

---

## 架構重點

### 資料流

1.  **排程任務 (`app/scheduler.py`)**:
    - **凌晨 (00:00–06:00)**: `run_cmuh_master_data()` 執行，爬取所有合作醫院的完整科室、醫師及排班資料，寫入 `appointment_snapshots` 作為基礎資料（此時不抓即時進度）。
    - **看診時段 (07:00–23:00)**: 每 3 分鐘執行 `run_tracked_appointments()`，僅爬取使用者已訂閱追蹤的門診，並抓取即時叫號進度，最後觸發 `check_and_notify()` 檢查是否需要發送通知。
    - **上午 08:00**: `run_morning_tracked_snapshot_sync()` 執行，確保當日已追蹤的門診有最新的即時進度。

2.  **爬蟲 (`app/scrapers/`)**:
    - 所有爬蟲皆繼承自 `BaseScraper` (`app/scrapers/base.py`)。
    - 實作了 `CMUHScraper` (中國醫本院) 與 `CMUHHsinchuScraper` (新竹分院) 等。

3.  **快照寫入邏輯**:
    - 寫入邏輯具有**時段感知**能力，僅在門診時段開始後（如上午 08:00 後）才抓取 `current_number` (目前叫號)。
    - `current_number`, `total_quota`, `waiting_list` 等即時欄位只有在非 null 時才會更新，避免覆蓋已有的有效資料。

4.  **通知門檻**:
    - `check_and_notify()` 負責在剩餘號碼 ≤ 20、≤ 10、≤ 5 時觸發通知。
    - 透過 `notified_N` 旗標防止在同一門檻重複發送通知。

### 重要開發慣例

- **非同步資料庫操作**:
  `supabase-py` 是一個**同步**函式庫。為避免阻塞 FastAPI 的事件迴圈，所有資料庫呼叫都必須用 `asyncio.to_thread()` 包裹。
  ```python
  import asyncio
  from app.database import get_supabase

  supabase = get_supabase()
  result = await asyncio.to_thread(
      lambda: supabase.table("doctors").select("*").eq("id", doc_id).execute()
  )
  ```

- **設定管理**:
  所有設定值透過 `app.config.get_settings()` 函式讀取。該函式使用 `@lru_cache` 快取 `pydantic_settings.BaseSettings` 的實例，從 `.env` 檔案或環境變數載入組態。

- **Supabase 客戶端**:
  Supabase 客戶端為一個單例 (Singleton)，透過 `app/database.py` 的 `get_supabase()` 取得。此客戶端使用 `service_role_key`，擁有完整的後端存取權限。

- **時區**:
  所有爬蟲與通知邏輯皆使用**台灣時間 (UTC+8)**。請務必使用 `app/core/timezone.py` 中的輔助函式 (`now_tw()`, `today_tw_str()`, etc.)。儲存至資料庫的時間戳記應為 UTC 格式 (`now_utc_str()`)。

- **時段代碼**:
  資料庫與程式碼中統一使用中文 `"上午"`, `"下午"`, `"晚上"`。爬蟲 API 的 `period` 參數則對應為 `"1"`, `"2"`, `"3"`。

### 新增醫院流程

1.  在 `app/scrapers/` 目錄下建立新的爬蟲類別，繼承 `BaseScraper`。
2.  設定 `HOSPITAL_CODE` 類別屬性，用於對應資料庫中的醫院記錄。
3.  實作 `fetch_departments()`, `fetch_schedule()`, `fetch_clinic_progress()` 三個抽象方法。
4.  在 `app/scheduler.py` 的 `run_cmuh_master_data()` 和 `run_tracked_appointments()` 中，將新的爬蟲類別加入 `scrapers` 列表。

### 資料庫結構 (Supabase)

- `hospitals`, `departments`, `doctors`: 核心主資料。
- `appointment_snapshots`: 儲存爬取到的門診狀態快照，以 `doctor_id`, `session_date`, `session_type` 作為 `upsert` 的衝突鍵。
- `tracking_subscriptions`: 使用者的追蹤訂閱紀錄，包含通知設定 (`notify_at_20/10/5`) 與狀態旗標 (`notified_20/10/5`)。
- `users_local`: 自訂的使用者資料表，包含 `is_admin`, `line_user_id`, `hashed_password` 等欄位。
- `notification_logs`: 所有通知嘗試的稽核記錄。

### API 結構

- 所有 API 路由皆以 `/api` 為前綴。
- 路由模組化存放於 `app/api/` 下，如 `auth`, `users`, `hospitals`, `tracking` 等。
- 認證依賴：一般路由使用 `get_current_user`，管理員路由使用 `get_current_admin`。

---

## 常用指令

### 執行與測試

```bash
# 啟動開發伺服器
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 執行所有非 UI 測試 (單元測試與整合測試)
pytest tests/ --ignore=tests/e2e -v --tb=short

# 執行單一測試檔案或函式
pytest tests/unit/test_scheduler_logic.py::TestClassName::test_method_name -v

# 僅執行單元測試
pytest tests/ -m unit -v

# 僅執行整合測試
pytest tests/ -m integration -v

# 執行 UI/Selenium 端對端測試 (需先啟動伺服器)
SELENIUM_HEADLESS=true pytest tests/e2e/test_ui_selenium.py -v -s --tb=short

# 手動觸發爬蟲 (需先啟動伺服器)
curl -X POST http://localhost:8000/api/admin/scrape-now
```
**注意**: `pytest.ini` 已設定 `asyncio_mode = auto`，非同步測試不需額外裝飾器。

### Supabase CLI 工具 (`tools/tool_supabase.py`)

> ⚠️ **強制規範**: 為了提升效率並標準化操作，所有需要直接讀寫 Supabase 資料的場景，**必須優先使用**此工具。

此工具提供了一個命令列介面，用於快速查詢、新增、修改、刪除 Supabase 資料。

**使用範例**:
```bash
# 列出所有醫院
python tools/tool_supabase.py list_hospitals

# 查詢特定科室的醫生
python tools/tool_supabase.py list_doctors --department_id <科室ID>

# 查詢使用者的訂閱
python tools/tool_supabase.py get_subscriptions <使用者ID>

# 通用查詢 (支持多個篩選條件)
python tools/tool_supabase.py select appointment_snapshots --filter doctor_id eq <醫生ID> --filter session_date gte 2026-03-01 --limit 10

# 更新資料
python tools/tool_supabase.py update tracking_subscriptions --filter user_id eq <使用者ID> --data '{"notify_at_20":false}'

# 插入或更新 (Upsert)
python tools/tool_supabase.py upsert appointment_snapshots --data '{"doctor_id":"<醫生ID>","session_date":"2026-03-05","session_type":"上午","current_number":5}' --on_conflict "doctor_id,session_date,session_type"
```

### Notion CLI 工具 (`tools/tool_notion.py`)

> ⚠️ **強制規範**: 所有需要讀寫 Notion 資料的場景，**必須優先使用**此工具，並預先設定 `NOTION_API` 環境變數。

此工具提供了一個命令列介面，用於快速查詢與管理 Notion 中的項目。

**使用範例**:
```bash
# 列出所有項目
python tools/tool_notion.py list_projects

# 查詢 "進行中" 的項目
python tools/tool_notion.py query_projects --filter Status is "進行中"

# 創建新項目
python tools/tool_notion.py create_project --data '{"Name":"新功能開發","Status":"計劃中"}'

# 更新項目
python tools/tool_notion.py update_project <頁面ID> --data '{"Status":"已完成"}'

# 獲取所有可用的資料庫
python tools/tool_notion.py get_databases
```

---

## 環境變數

- **必填**: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY`, `SECRET_KEY`
- **選填**:
  - `SMTP_*` (SMTP 伺服器相關設定)
  - `LINE_CHANNEL_ACCESS_TOKEN`, `LINE_CHANNEL_SECRET`
  - `SCRAPE_INTERVAL_MINUTES` (爬蟲間隔分鐘數，預設為 3)
  - `NOTION_API` (Notion 整合權杖，`tool_notion.py` 必填)

---

## 開發與提交慣例

### Git 指引

- **分支策略**:
  - 使用 `feature/<功能描述>` 的格式建立新功能分支，例如 `feature/add-line-notification`。
  - 完成後，透過 Pull Request (PR) 合併至 `main` 分支。
  - 所有 PR 必須經過至少一位團隊成員的 Code Review。

- **Commit Message**:
  - **使用英文撰寫**。
  - 格式: `<type>(<scope>): <subject>`
  - `<type>`: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`
  - `<scope>`: 相關模組或功能的簡短描述 (例如: `scheduler`, `api`, `scraper`)
  - `<subject>`: 具體的變更說明，不超過 72 字元。
  - 範例: `feat(scheduler): add new hospital scraper`

- **版本標籤**:
  - 使用語義化版本控制 (`v<MAJOR>.<MINOR>.<PATCH>`)。
  - `MAJOR`: 不相容的 API 修改。
  - `MINOR`: 向下相容的功能新增。
  - `PATCH`: 向下相容的錯誤修復。
  - 範例: `v1.2.0`

### Code Review 指引

在進行 Code Review 時，請重點檢查以下項目：
1.  **符合規範**: 程式碼是否遵循專案的程式碼風格與上述開發慣例。
2.  **測試覆蓋**: 變更有無適當的單元測試或整合測試。
3.  **清晰度**: Commit Message 和 PR 描述是否清晰明瞭。
4.  **文件**: 是否有對應的文件更新 (docstrings, `/docs` 目錄等)。
5.  **效能與安全**: 是否有潛在的效能瓶頸或安全風險。
6.  **錯誤處理**: 是否已妥善處理各種邊界條件與錯誤情境。
7.  **可讀性**: 程式碼是否清晰易懂，變數與函式命名是否具備意義。
8.  **非同步處理**: 是否正確使用 `asyncio.to_thread` 處理同步 I/O。

---

## 🛠️ 自動化與安全規範 (專屬此專案)

-   **自動執行授權**: 針對本專案中所有在 `/tmp` 目錄下建立、讀取、分析用的 Python 或 Shell 腳本，Antigravity 獲授權可將 `SafeToAutoRun` 設為 `true` 直接執行。
-   **資料庫分析**: 允許自動執行查詢並輸出結果到 `/tmp` 的分析腳本，以提升數據清理與診斷的效率。
-   **安全性限制**: 涉及刪除 `app/` 目錄下的原始碼、修改環境變數 `.env`、或影響 PM2 生產環境服務時，仍必須請求使用者同意。
