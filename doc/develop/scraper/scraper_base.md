# 爬蟲基礎架構 (BaseScraper)

本文件說明 `app/scrapers/base.py` 中定義的爬蟲基礎類別與整體共用的資料結構，以及其與 Scheduler、Supabase 的互動機制。

## 主要資料結構 (Data Classes)

所有實作的醫院爬蟲必須回傳以下標準化資料結構：

1. **`DepartmentData`**: 科室基本資料。
   - `name`: 科室名稱 (例如：一般內科)
   - `code`: 科室代碼 (用於後續爬取門診表)
   - `hospital_code`: 醫院代碼
   - `category`: 科室分類 (例如：內科系、外科系)

2. **`DoctorSlot`**: 醫生門診時段資料。
   - `doctor_no`: 醫生代號
   - `doctor_name`: 醫生姓名
   - `department_code`: 所屬科室代碼
   - `session_date`: 門診日期
   - `session_type`: 時段 (`上午`, `下午`, `晚上`)
   - `clinic_room`: 診間代號/名稱
   - `is_full`: 是否額滿
   - `status`: 門診狀態 (例如：額滿、停診、代診)

3. **`ClinicProgress`**: 即時看診進度資料。
   - `clinic_room`: 診間名稱
   - `session_type`: 時段
   - `current_number`: 目前叫號
   - `total_quota`: 總名額 (Max Number)
   - `registered_count`: 已掛號人數 (Headcount)
   - `status`: 狀態 (例如：看診中、看診完畢、未開診)
   - `waiting_list`: 尚未看診的號碼清單
   - `clinic_queue_details`: 詳細排隊狀態列表

## 爬蟲基礎介面 (`BaseScraper`)

所有醫院專用爬蟲都必須繼承 `BaseScraper` 並實作以下抽象方法：

- **`fetch_departments(self) -> list[DepartmentData]`**:
  抓取該醫院的所有科室清單。

- **`fetch_schedule(self, dept_code: str) -> list[DoctorSlot]`**:
  根據科室代碼，抓取該科室所有醫生的門診排班表與掛號狀態。這通常用於「快照」機制。

- **`fetch_clinic_progress(self, room: str, period: str, **kwargs) -> Optional[ClinicProgress]`**:
  根據診間與時段，抓取「目前的即時叫號進度」。這是在門診看診時間內，系統高頻率（每3分鐘）呼叫的 API。

- **`calculate_remaining_count(self, current_number: int, target_number: int, clinic_queue_details: list[dict]) -> int`**:
  計算使用者預約號碼 (`target_number`) 與當前號碼 (`current_number`) 之間，還有多少人未看診。因各家醫院對於「過號」、「退掛」、「完成」的顯示邏輯不同，因此交由各爬蟲自行實作。

## 共用機制 (Common Mechanisms)

### 1. 標準化重試機制 (Standardized Retry)
所有醫院爬蟲的網路請求皆整合了 `tenacity` 函式庫，並遵循以下標準化重試策略：
- **重試次數**: 最多 3 次 (含初始嘗試)。
- **等候時間**: 固定 5 秒 (`wait_fixed(5)`)。
- **適用範圍**: 核心網路方法如 `_get`, `_post` 或 `fetch_departments` 等。

這是為了確保在面對醫院伺服器暫時性不穩或 WAF 誤導時，系統能有基本的容錯能力。

## 與 Scheduler 的互動機制

`app/scheduler.py` 負責調度爬蟲任務，主要分為兩種模式：

1. **基礎資料抓取 (`run_master_data`)**:
   - **時段**: 每天凌晨 00:00 - 06:00
   - **流程**: 遍歷啟用的爬蟲 -> 呼叫 `fetch_departments` -> 呼叫 `fetch_schedule`。
   - **用途**: 將未來一個月的班表寫入資料庫，建立 `appointment_snapshots`，但不抓取即時進度（此時通常未開診）。

2. **即時進度追蹤 (`run_tracked_appointments`)**:
   - **時段**: 每天 07:00 - 23:00 (每 3 分鐘執行)
   - **流程**: 查詢 Supabase 找出目前有使用者「正在追蹤」的醫生與科室 -> 針對這些標的呼叫 `fetch_schedule` 更新掛號額度 -> 如果是今天的門診，且在看診時段內，再呼叫 `fetch_clinic_progress` 取得即時叫號。
   - **用途**: 更新目前的燈號進度 `current_number` 與等待人數 `waiting_count`。

## 與 Supabase 的互動機制

爬蟲本身不直接讀寫 Supabase。資料庫操作統一在 `scheduler.py` 與 `app/services/data_writer.py` 中處理：

- `upsert_department`: 將 `DepartmentData` 寫入/更新 `departments` 表。
- `upsert_doctor`: 將 `DoctorSlot` 中的醫生資訊寫入/更新 `doctors` 表。
- `batch_insert_snapshots`: 將門診與進度資料合併後，執行 Upsert 寫入 `appointment_snapshots` 表（以 `doctor_id`, `session_date`, `session_type` 為唯一鍵）。
- 全部的 Supabase 呼叫都透過 `asyncio.to_thread` 執行，以避免阻塞 FastAPI 的 Async 事件迴圈。
