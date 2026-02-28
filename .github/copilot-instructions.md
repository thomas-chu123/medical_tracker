# Copilot 指引

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

### 環境變數

必填：`SUPABASE_URL`、`SUPABASE_SERVICE_ROLE_KEY`、`SUPABASE_ANON_KEY`、`SECRET_KEY`  
選填：`SMTP_*` 相關變數、`LINE_CHANNEL_ACCESS_TOKEN`、`LINE_CHANNEL_SECRET`、`SCRAPE_INTERVAL_MINUTES`（預設：3）

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

/temp 放置臨時文件或測試腳本，請確保這些文件不會被提交到版本控制系統中，並且在不再需要時及時清理。

