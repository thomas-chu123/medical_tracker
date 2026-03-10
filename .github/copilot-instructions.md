# Copilot 指引

## ⚠️ 重要語言指示

**所有回覆都必須使用繁體中文 (Traditional Chinese)**

- ✅ 使用繁體中文
- ❌ 不使用簡體中文、英文或其他語言
- ✅ 代碼註釋: 繁體中文
- ✅ Git 提交信息: 英文（按照專案慣例）
- ✅ PR 描述: 英文（按照專案慣例）
- ✅ Code review 評論: 繁體中文
- ✅ 文件說明: 繁體中文, 放置於 `/docs` 目錄
- ✅ 回覆內容: 繁體中文

---

## 專案概述

台灣醫療門診追蹤系統。每 3 分鐘自動爬取醫院門診叫號資料，在使用者掛號號碼即將到時，透過 Email 或 LINE 發送通知。

## 技術堆疊

- **後端**：FastAPI + APScheduler + Supabase（透過 supabase-py 存取 PostgreSQL）
- **爬蟲**：httpx + BeautifulSoup4/selectolax
- **認證**：自訂 JWT（python-jose + bcrypt/passlib），使用者資料存於 `users_local` Supabase 資料表，**並非** Supabase Auth
- **通知**：aiosmtplib（電子郵件）+ LINE Messaging API
- **前端**：靜態 SPA，由 `static/` 目錄提供服務

## 指令

```bash
# 啟動開發伺服器
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 執行所有非 UI 測試（不需要啟動伺服器）
pytest tests/ --ignore=tests/test_ui_selenium.py --ignore=tests/test_ui_e2e_minimal.py -v --tb=short

# 執行單一測試
pytest tests/test_scheduler_logic.py::TestClassName::test_method_name -v

# 執行單元測試
pytest tests/ -m unit -v

# 執行整合測試
pytest tests/ -m integration -v

# 執行 UI/Selenium 測試（需要啟動伺服器與 Chrome）
SELENIUM_HEADLESS=true pytest tests/test_ui_selenium.py -v -s --tb=short

# 手動觸發爬蟲（需要伺服器運行中）
curl -X POST http://localhost:8000/api/admin/scrape-now
```

**pytest 設定**：`asyncio_mode = auto`，所有 async 測試不需要額外的裝飾器。Allure 報告輸出至 `allure-results/`。

## 架構

### 資料流

1. **APScheduler** 在 `app/scheduler.py` 執行排程任務：
   - **00:00–06:00**：`run_cmuh_master_data()` — 爬取完整科室／醫師／排班資料，寫入 `appointment_snapshots`（不抓即時進度）
   - **07:00–23:00** 每 3 分鐘：`run_tracked_appointments()` — 僅爬取有 `tracking_subscriptions` 的科室與醫師，若門診時段已開始則抓取即時叫號進度，最後呼叫 `check_and_notify()`
   - **08:00 AM**：`run_morning_tracked_snapshot_sync()` — 刷新今日已追蹤門診的即時進度

2. **爬蟲** 繼承 `BaseScraper`（`app/scrapers/base.py`），需實作三個抽象方法：
   - `fetch_departments()` → `list[DepartmentData]`
   - `fetch_schedule(dept_code)` → `list[DoctorSlot]`
   - `fetch_clinic_progress(room, period)` → `Optional[ClinicProgress]`
   - 目前已實作：`CMUHScraper`（本院）與 `CMUHHsinchuScraper`（新竹分院），位於 `app/scrapers/cmuh.py`

3. **快照寫入邏輯**：`scheduler.py` 中的 `_build_snapshot_row()` 具有時段感知能力 — 僅在門診時段開始後（上午 ≥ 08:00、下午 ≥ 13:30、晚上 ≥ 18:00）且僅針對已追蹤的門診才抓取 `current_number`。`current_number`、`total_quota`、`waiting_list` 等欄位只有在非 null 時才會寫入，以避免覆蓋先前爬取到的即時進度。

4. **通知門檻**：`check_and_notify()` 在剩餘號碼 ≤ 20、≤ 10、≤ 5 時觸發。每個門檻對應訂閱上的 `notified_N` 旗標，防止重複通知。

### 重要慣例

**Supabase 呼叫皆為同步**（supabase-py 是 sync 客戶端）— 每次 DB 呼叫必須用 `asyncio.to_thread()` 包裹，避免阻塞事件迴圈：
```python
result = await asyncio.to_thread(
    lambda: supabase.table("doctors").select("*").eq("id", doc_id).execute()
)
```

**設定值** 透過 `get_settings()`（`@lru_cache` 快取）從 `pydantic_settings.BaseSettings` 讀取，來源為環境變數或 `.env` 檔案。

**Supabase 客戶端** 為 singleton，透過 `app/database.py` 的 `get_supabase()` 取得，使用 service role key（非 anon key）。

**時區**：所有爬蟲與通知邏輯使用台灣時間（UTC+8）。請使用 `app/core/timezone.py` 中的輔助函式：`now_tw()`、`today_tw()`、`today_tw_str()`、`now_utc_str()`。儲存至 DB 的時間戳記使用 UTC（`now_utc_str()`），但 `session_date` 的比較使用台灣本地日期。

**時段代碼**：使用中文 `"上午"` / `"下午"` / `"晚上"`。爬蟲 API 的 period 參數對應 `"1"` / `"2"` / `"3"`。

**密碼雜湊**：bcrypt 前會將密碼截斷至 71 bytes，以避免 >72 bytes 的錯誤，此為刻意設計。

### 新增醫院

1. 在 `app/scrapers/` 建立繼承 `BaseScraper` 的新爬蟲類別
2. 設定 `HOSPITAL_CODE` 類別屬性（用於查詢 DB 中的醫院記錄）
3. 實作三個抽象方法
4. 在 `app/scheduler.py` 的 `run_cmuh_master_data()` 與 `run_tracked_appointments()` 中，將新爬蟲加入 `scrapers` 列表

### 資料庫結構（Supabase）

- `hospitals`、`departments`、`doctors` — 主資料
- `appointment_snapshots` — 爬取的門診狀態（以 doctor_id + session_date + session_type 為衝突鍵進行 upsert）
- `tracking_subscriptions` — 使用者追蹤訂閱，包含 `notify_at_20/10/5` 設定與 `notified_20/10/5` 狀態旗標
- `users_local` — 自訂使用者資料表（非 Supabase Auth），欄位包含 `is_admin`、`line_user_id`、`hashed_password`
- `notification_logs` — 每次通知嘗試的稽核記錄

### API 結構

所有路由前綴為 `/api`。路由模組：`auth`、`users`、`hospitals`、`tracking`、`stats`、`snapshots`、`admin`、`webhooks`（LINE Message API webhook）。

認證依賴：一般路由使用 `get_current_user`，管理員路由使用 `get_current_admin`，皆位於 `app/auth.py`。

## 開發工具與工作流程

### 工具概述

本專案提供多個 CLI 工具協助開發和除錯，所有工具位於 `tools/` 目錄：

| 工具 | 用途 | 路徑 |
|------|------|------|
| `tool_supabase.py` | 快速查詢和修改 Supabase 數據庫 | `tools/tool_supabase.py` |
| `tool_notion.py` | 快速查詢和修改 Notion 項目 | `tools/tool_notion.py` |

### 工具使用方式

#### 運行工具的基本方式

```bash
# 在項目根目錄運行工具
python tools/tool_supabase.py <command> [options]
python tools/tool_notion.py <command> [options]

# 帶 cd 進項目目錄
cd /path/to/medical_help
python tools/tool_supabase.py list_hospitals
```

#### 在 Copilot Chat 中使用工具

1. **查詢數據**：直接要求工具執行查詢
   ```
   "查詢馬偕醫院的眼科醫生"
   → Copilot 會自動執行: python tools/tool_supabase.py list_doctors --department_id <眼科ID>
   ```

2. **修改數據**：明確指定更新內容
   ```
   "更新用戶 user123 的追蹤設定"
   → Copilot 會執行 update 或 upsert 操作
   ```

3. **調試問題**：使用工具驗證數據
   ```
   "檢查為什麼眼科沒有醫生"
   → Copilot 會查詢相關表格並分析
   ```

#### 工具執行環境要求

- Python 3.8+
- 環境變數已設定：`SUPABASE_URL`、`SUPABASE_SERVICE_ROLE_KEY`
- 對於 Notion 工具：`NOTION_API` 環境變數已設定

### Supabase 讀寫工具 (CLI & Copilot Chat)

> ⚠️ **強制規範**：所有需要讀寫 Supabase 資料的 prompt 操作，**必須優先使用** `tools/tool_supabase.py`，禁止直接呼叫 MCP Supabase 工具或在 CLI 環境中撰寫臨時 Python 腳本存取資料庫。

為了提升效率並避免 MCP 使用緩慢的問題，提供了獨立的 Python CLI 工具 `tools/tool_supabase.py`，供 Copilot Chat 與 Copilot CLI 快速讀寫 Supabase 資料。

#### 基本使用方式

```bash
# 列出所有醫院
python tools/tool_supabase.py list_hospitals

# 列出特定科室的醫生
python tools/tool_supabase.py list_doctors --department_id DEPT001

# 查詢使用者訂閱
python tools/tool_supabase.py get_subscriptions user123

# 查詢特定表格的資料（支持多個篩選條件）
python tools/tool_supabase.py select appointment_snapshots --filter doctor_id eq DOC001 --filter session_date gte 2026-03-01 --limit 100

# 插入新資料
python tools/tool_supabase.py insert users_local --data '{"email":"test@example.com","hashed_password":"...","is_admin":false}'

# 更新資料（支持多個篩選條件）
python tools/tool_supabase.py update tracking_subscriptions --filter user_id eq user123 --filter doctor_id eq DOC001 --data '{"notify_at_20":false}'

# Upsert (插入或更新)
python tools/tool_supabase.py upsert appointment_snapshots --data '{"doctor_id":"DOC001","session_date":"2026-03-05","session_type":"上午","current_number":5}' --on_conflict "doctor_id,session_date,session_type"

# 刪除資料
python tools/tool_supabase.py delete tracking_subscriptions --filter user_id eq user123 --filter doctor_id eq DOC001

# 獲取醫生的最新快照記錄
python tools/tool_supabase.py get_latest_snapshots DOC001 --limit 20
```

#### 支持的操作符

- `eq` — 相等
- `neq` — 不相等
- `gt` / `gte` — 大於 / 大於等於
- `lt` / `lte` — 小於 / 小於等於
- `like` — 模糊匹配 (LIKE)
- `in` — 包含（值用逗號分隔）

#### 便捷方法（Convenience Methods）

| 命令 | 說明 |
|------|-----|
| `list_hospitals` | 列出所有醫院 |
| `list_departments [--hospital_id ID]` | 列出科室（可選篩選醫院） |
| `list_doctors [--department_id ID]` | 列出醫生（可選篩選科室） |
| `get_user USER_ID` | 獲取使用者資訊 |
| `get_subscriptions USER_ID` | 獲取使用者的所有訂閱 |
| `get_latest_snapshots DOC_ID [--limit N]` | 獲取醫生的最新快照記錄 |

#### 返回格式

所有命令返回 JSON，包含：
```json
{
  "status": "success|error",
  "count": 5,
  "data": [...],
  "message": "error message if applicable"
}
```

#### 何時使用此工具

- ✅ 快速查詢和修改資料庫記錄
- ✅ 驗證 Supabase 中的資料
- ✅ 執行一次性的資料操作
- ✅ 在 Copilot Chat 中詢問資料庫狀態
- ❌ 不適合複雜的異步 API 邏輯（應在 FastAPI 程式碼中實作）

### Notion 讀寫工具 (CLI & Copilot Chat)

> ⚠️ **強制規範**：所有需要讀寫 Notion 資料的 prompt 操作，**必須優先使用** `tools/tool_notion.py`，禁止直接呼叫 MCP Notion 工具或在 CLI 環境中撰寫臨時腳本存取 Notion。需先設定 `NOTION_API` 環境變數。

為了提升效率並避免 MCP 使用緩慢的問題，提供了獨立的 Python CLI 工具 `tools/tool_notion.py`，供 Copilot Chat 與 Copilot CLI 快速讀寫 Notion 項目資料。

#### 基本使用方式

```bash
# 列出所有項目（默認第一個數據庫）
python tools/tool_notion.py list_projects

# 列出特定數據庫的項目
python tools/tool_notion.py list_projects --database_id <database_id>

# 查詢項目（支持篩選和排序）
python tools/tool_notion.py query_projects --filter Status is "進行中" --sort_property CreatedDate --sort_direction descending

# 獲取單個項目的詳細信息
python tools/tool_notion.py get_project 123e4567e89b12d3a456426614174000

# 創建新項目
python tools/tool_notion.py create_project --data '{"Name":"新項目","Status":"計劃中"}'

# 創建新項目至指定數據庫
python tools/tool_notion.py create_project --database_id <database_id> --data '{"Name":"新項目","Status":"計劃中"}'

# 更新項目
python tools/tool_notion.py update_project 123e4567e89b12d3a456426614174000 --data '{"Status":"進行中"}'

# 列出所有可用的數據庫
python tools/tool_notion.py get_databases

# 獲取數據庫結構（屬性/列信息）
python tools/tool_notion.py get_database_schema <database_id>
```

#### 支持的篩選操作符

- `is` — 相等
- `is_not` — 不相等
- `contains` — 包含
- `does_not_contain` — 不包含
- `starts_with` — 開始於
- `ends_with` — 結尾於

#### 便捷方法（Convenience Methods）

| 命令 | 說明 |
|------|-----|
| `list_projects [--database_id ID]` | 列出項目（可選指定數據庫） |
| `get_project PAGE_ID` | 獲取單個項目詳情 |
| `query_projects [--filter PROPERTY OP VALUE] [--database_id ID] [--sort_property PROP] [--sort_direction DESC\|ASC]` | 查詢項目（支持篩選和排序） |
| `create_project --data JSON [--database_id ID]` | 創建新項目 |
| `update_project PAGE_ID --data JSON` | 更新項目 |
| `get_databases` | 列出所有數據庫 |
| `get_database_schema DATABASE_ID` | 獲取數據庫結構信息 |

#### 返回格式

所有命令返回 JSON，包含：
```json
{
  "status": "success|error",
  "count": 5,
  "data": [...],
  "message": "error message if applicable"
}
```

#### 何時使用此工具

- ✅ 快速查詢和修改 Notion 項目資料
- ✅ 驗證 Notion 中的項目狀態
- ✅ 執行一次性的項目操作
- ✅ 列出所有可用的 Notion 數據庫和結構
- ✅ 在 Copilot Chat 中詢問 Notion 項目狀態
- ❌ 不適合批量操作（超過 100 個項目）
- ❌ 不適合複雜的關聯邏輯（應在 FastAPI 程式碼中實作）

### 環境變數

必填：`SUPABASE_URL`、`SUPABASE_SERVICE_ROLE_KEY`、`SUPABASE_ANON_KEY`、`SECRET_KEY`  
選填：`SMTP_*` 相關變數、`LINE_CHANNEL_ACCESS_TOKEN`、`LINE_CHANNEL_SECRET`、`SCRAPE_INTERVAL_MINUTES`（預設：3）、`NOTION_API`（Notion 整合 Token，tool_notion.py 必填）

### 其他

commit message 格式: 使用英文書寫，格式為 `<type>(<scope>): <subject>`，其中 `<type>` 為 feat、fix、docs、style、refactor、test、chore 之一，`<scope>` 為相關模組或功能的簡短描述，`<subject>` 為具體的變更說明（不超過 72 字）。例如：`feat(scheduler): add new hospital scraper`。

chat response 格式：請使用中文撰寫，保持專業且簡潔。回答應直接針對問題，避免冗長的背景說明或不必要的細節。

git 分支策略：使用 feature 分支開發新功能，命名格式為 `feature/<功能描述>`，例如 `feature/add-notification-logs`。完成後透過 pull request 合併至 main 分支，並由其他團隊成員進行 code review。

git tag 策略：使用語義化版本控制，tag 格式為 `v<MAJOR>.<MINOR>.<PATCH>`，例如 `v1.2.0`。當有重大變更或不相容的 API 修改時增加 MAJOR 版本；當新增功能但保持向下兼容時增加 MINOR 版本；當修復錯誤或進行小改動時增加 PATCH 版本。

code review 指引：在 code review 時，請檢查以下幾點：
1. 代碼是否符合專案的程式碼風格和最佳實踐。
2. 變更是否有適當的測試覆蓋。
3. 變更是否有清晰的 commit message 和 pull request 描述。
4. 變更是否有適當的文件更新（如有必要）。
5. 變更是否有潛在的性能問題或安全風險。
6. 變更是否有適當的錯誤處理和邊界條件考慮。
7. 變更是否有適當的抽象和模組化，避免重複代碼。
8. 變更是否有適當的日誌記錄（如有必要）。
9. 變更是否有適當的資源管理（如有必要），避免內存洩漏或資源浪費。
10. 變更是否有適當的用戶體驗考慮（如有必要），確保功能易於使用且符合用戶需求。
11. 變更是否有適當的國際化和本地化考慮（如有必要），確保功能適用於不同地區和語言的用戶。
12. 變更是否有適當的可維護性和可擴展考慮，確保代碼易於理解和修改。
13. 變更是否有適當的依賴管理，確保不引入不必要的依賴或版本衝突。
14. 變更是否有適當的性能優化，確保不引入性能瓶頸或資源浪費。
15. 變更是否有適當的安全考慮，確保不引入安全漏洞或敏感信息泄露。
16. 變更是否有適當的合規性考慮，確保不違反相關法律法規或行業標準。
17. 變更是否有適當的可測試性考慮，確保代碼易於編寫和執行測試。
18. 變更是否有適當的可讀性考慮，確保
代碼清晰易懂，使用有意義的變量和函數名稱。
19. 變更是否有適當的可重用性考慮，確
保代碼可以在不同上下文中重用，避免硬編碼和緊耦合。
20. 變更是否有適當的文檔更新，確保代碼
的功能和使用方式有清晰的文檔說明，便於其他開發者理解和使用。
21. 變更是否有適當的回滾計劃，確保在發現問題時可以快速回滾到穩定版本。

/docs 相關：請確保所有公共 API 和重要功能都有適當的文檔說明，使用 docstring 格式，並包含參數說明、返回值說明和示例（如有必要）。文檔應該清晰、簡潔且易於理解，避免使用過於技術性的術語或行話。

### 開發工具與臨時文件信任設定

為了提升開發效率，以下路徑下的所有操作 **自動信任，無需批准**：

**信任路徑**：
1. `/tmp/*` — 臨時檔案和開發腳本（自動批准理由：純粹開發輔助工具，不影響項目代碼）
2. `./temp/*` — 項目本地臨時文件夾
3. `*/cache/*` — 快取相關文件
4. `./tests/*` — 測試文件和測試腳本（自動批准理由：測試代碼，驗證功能不破壞核心邏輯）
5. `./tools/*` — CLI 工具和開發輔助指令（自動批准理由：開發工具，協助資料庫查詢和項目管理）

**允許的操作**：
- ✅ 創建、修改、更新 Python 和 Shell 腳本
- ✅ 修改臨時測試數據或日誌文件
- ✅ 執行 `/tmp`、`./tests/`、`./tools/` 目錄下的任何腳本或命令（包括資料庫查詢、API 測試等）
- ✅ 刪除過期的臨時文件和舊的測試文件
- ✅ 撰寫新的測試用例和測試工具
- ✅ 新增或更新 CLI 工具指令

**重要提醒**：
- `/tmp` 下的所有變更 **都不會被提交到 Git**（此目錄已在 `.gitignore` 中）
- `./tests/` 和 `./tools/` 目錄下的變更 **會被提交到 Git**（請確保代碼品質）
- 臨時腳本完成後應移至 `tools/` 目錄或刪除，避免重複代碼
- 不適用於項目核心代碼的修改（`app/` 仍需適當審查）

`./temp` 放置臨時文件或測試腳本，請確保這些文件不會被提交到版本控制系統中，並且在不再需要時及時清理。`./tests` 和 `./tools` 目錄下的變更會被納入版本控制，請確保代碼品質和文檔完整性。

## 爬蟲調試指南

### 常見問題與解決方案

#### 1. 科室列表為空或不完整
**症狀**：爬蟲無法獲取科室列表，導致 `fetch_departments()` 返回空列表。

**檢查步驟**：
1. 使用工具驗證數據庫中是否有科室記錄：
   ```bash
   python tools/tool_supabase.py list_departments --hospital_id <hospital_id>
   ```
2. 查看爬蟲日誌中的 `[HOSPITAL] Built dynamic registration ID map` 信息
3. 檢查目標網站是否使用 JavaScript 動態加載內容（可使用 Chrome 開發者工具查看）

**根本原因**：
- 目標網站使用 JavaScript 動態加載（常見的 Cloudflare DDoS 保護、Vue.js 等框架）
- httpx 無法執行 JavaScript，因此無法獲得實際內容

**解決方案**：
- 使用 Selenium 或 Playwright 代替 httpx 以支持 JavaScript 執行
- 或改用其他數據源（如 API endpoint、HTML 伺服器端渲染的部分）

#### 2. 醫生列表為空

**症狀**：科室正確，但無法獲取該科室的醫生列表。

**檢查步驟**：
1. 驗證科室代碼是否正確：
   ```bash
   python tools/tool_supabase.py select doctors --filter department_id eq <dept_id> --limit 10
   ```
2. 檢查爬蟲日誌中 `fetch_schedule` 的輸出，查看是否成功解析了 HTML
3. 使用調試腳本直接抓取網頁： 
   ```python
   import httpx
   import re
   from bs4 import BeautifulSoup
   
   # 直接抓取醫生排班頁面 HTML，檢查表格結構
   resp = httpx.get("https://hospital.com/schedule?dept=45")
   soup = BeautifulSoup(resp.text, "lxml")
   table = soup.find("table", id="tblSch")
   if table:
       rows = table.find_all("tr")
       print(f"Found {len(rows)} rows")
   ```

**根本原因**：
- HTML 表格結構已改變（網站更新）
- 科室代碼映射不匹配（使用了錯誤的 depid）
- 該科室確實沒有醫生排班（如某些特殊門診）

**解決方案**：
1. 檢查網站的實際 HTML 結構並更新爬蟲的解析邏輯
2. 驗證科室代碼是否正確（可對比網站上的 URL 參數）
3. 確認該科室是否為有效的臨床科室

#### 3. 特定醫院爬蟲失敗

**症狀**：某個醫院的爬蟲無法正常工作。

**診斷步驟**：
1. 檢查該醫院是否已啟用：
   ```bash
   python tools/tool_supabase.py select hospitals --filter code eq HOSPITAL_CODE
   ```
2. 查看 `app/scheduler.py` 中是否包含該醫院的爬蟲
3. 檢查 `.env` 中是否設定了 `ENABLED_HOSPITALS`
4. 查看最近的爬蟲日誌，找出具體的錯誤信息

**常見原因**：
- 爬蟲未在 scheduler 中註冊
- 醫院代碼與數據庫中的代碼不匹配
- 網站結構已改變，爬蟲的 HTML 解析邏輯過時

### 調試技巧

#### 直接執行爬蟲進行測試
```bash
python << 'EOF'
import asyncio
from app.scrapers.hmmh import HMMHScraper

async def test():
    scraper = HMMHScraper()
    try:
        depts = await scraper.fetch_departments()
        print(f"Found {len(depts)} departments")
        
        for dept in depts[:3]:
            print(f"  {dept.name}: {dept.code}")
            schedule = await scraper.fetch_schedule(dept.code)
            print(f"    - {len(schedule)} slots")
    finally:
        await scraper.close()

asyncio.run(test())
EOF
```

#### 保存並檢查 HTML 內容
```bash
# 檢查爬蟲實際抓取的 HTML 內容
python << 'EOF'
import asyncio
import httpx
from bs4 import BeautifulSoup

async def debug_html():
    async with httpx.AsyncClient() as client:
        resp = await client.get("https://hospital.com/page")
        with open("/tmp/debug.html", "w") as f:
            f.write(resp.text)
        print(f"Saved {len(resp.text)} bytes to /tmp/debug.html")

asyncio.run(debug_html())
EOF

# 然後在瀏覽器中打開 /tmp/debug.html 查看實際內容
```

#### 比較不同時間的爬蟲輸出
```bash
# 記錄爬蟲的日誌輸出並比較
grep "HMMH\|CMUH\|NTUH" logs/app.log | tail -100
```

### 工具集成示例

查詢眼科沒有醫生的原因（如本項目曾遇到的問題）：

```bash
# 1. 查詢眼科科室是否存在
python tools/tool_supabase.py select departments --filter name like 眼科 --limit 5

# 2. 查詢該科室的醫生數
python tools/tool_supabase.py select doctors --filter department_id eq <dept_id>

# 3. 檢查爬蟲日誌
grep "眼科\|депt_code" logs/app.log | tail -50

# 4. 手動運行爬蟲以進行調試
python -c "from app.scrapers.hmmh import HMMHScraper; import asyncio; asyncio.run(HMMHScraper().fetch_departments())" 2>&1 | grep -i 眼科
```

