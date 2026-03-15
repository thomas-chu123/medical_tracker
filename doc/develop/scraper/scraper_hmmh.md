# 馬偕紀念醫院新竹分院 (HMMH) 爬蟲機制

本文件說明 `app/scrapers/hmmh.py` 中實作的新竹馬偕紀念醫院 (HMMH) 爬蟲運作原理。

## 運作原理與機制

HMMH 爬蟲使用的是純 HTTP GET/POST 請求，搭配 `httpx.AsyncClient` 與 `BeautifulSoup` (lxml 解析器)。最大的特色在於**完全不依賴 AJAX 或 Selenium**，網站所有資訊（包含一週排班表與醫生代號）都是 Server-Side Rendering (SSR) 直接渲染在 HTML 中，減少了被阻擋的可能性，但會適時加入隨機延遲 `asyncio.sleep` 以降低對目標伺服器的壓力。

## 爬蟲流程與主要 API

### 1. 取得科室清單 (`fetch_departments`)
- **API URL**: `/progress.php` 與 `/find_division.php`
- **流程**:
  1. HMMH 有兩套科室 ID 系統：掛號用的 `depid` (Registration ID) 與查進度用的 `dept` (Progress ID)。
  2. 爬蟲先請求 `/find_division.php` 嘗試建立 `Department Name -> Registration ID` 的對應表字典。為防被阻擋，也有一份常數 `DEPARTMENT_CODE_MAPPING` 做 fallback。
  3. 請求 `/progress.php` 取出下拉選單 `<select name="dept">`，將科室名稱配對正確的 Registration ID，做為科室代碼 (`code`)。

### 2. 取得門診表 (`fetch_schedule`)
- **API URL**: `/register_divide.php?depid={code}`
- **流程**:
  1. 向伺服器請求特定科室的一週排班表。
  2. 網頁表格 `<table id="tblSch">` 的儲存格同時包含：醫生姓名、醫生代號 (`drcode`)、以及另一個內部掛號代碼 (`internal_depid`)，且全寫死在 `onclick="registergo('{internal_depid}','{drcode}')"` 屬性中。
  3. 透過 Regex 拆解取出資訊，計算出每個時段（上午、下午、晚間）的日期，並建構出 `DoctorSlot`。
- **個別醫師詳細班表 (`fetch_single_doctor_schedule`)**:
  特定情況下（如掛號額滿與否），會再打 `/register_single_doctor.php?depid={}&drcode={}`，透過表格中的「初診(可掛)」、「複診(可掛)」、「滿號」字樣判定是否額滿。

### 3. 取得即時叫號進度 (`fetch_clinic_progress`)
- **API URL**: `/progressstatus.php?dept={dept_code}&ap={period}`
- **參數**: `ap` 為時段 (1=上午診, 2=下午診, 3=夜間診)
- **流程**: 
  1. `room` 參數在這裡實際上是代表 `dept` (Progress ID)。爬蟲會先透過 `_get_internal_dept_code` 轉換代碼。
  2. 爬取進度頁面，尋找 `<table class="regtable">`。
  3. 解析表格的欄位：位置、診別、醫師、目前看診號、未看診人數 (`waiting_count`)。
  4. 判斷全域狀態與個人狀態（例如「已停診」、「未開診」、「看診完畢」）。
- **輸出**: 回傳包含 `current_number` 與 `waiting_count` (由未看診人數提供) 的 `ClinicProgress`。

## 與 Scheduler / Supabase 的相依性

- **Internal Dept Code 緩存**: 新竹馬偕的科室、掛號與查詢系統代碼錯綜複雜。爬蟲在 `fetch_schedule` 時會順便把 `internal_dept_code` 暫存起來（放在 `self._internal_dept_cache`）。在 Schedule 模組準備打 `fetch_clinic_progress` 前，會依賴這個對應關係把正確參數帶入。
- **Waiting Count 提供**: HMMH 在進度頁面會直接提供「未看診人數」。`scheduler.py` 在抓到 `progress.waiting_count` 有值時，會將它存入 `appointment_snapshots`，這有助於後續看診速度 (`speed_estimator`) 的計算。
- **隨機 User-Agent 與延遲**: 因為馬偕有安裝 Cloudflare 或類似的防禦機制，會透過隨機選取 User-Agent (`RANDOM_USER_AGENTS`) 與請求前隨機暫停 (`_apply_random_delay`) 來避免 IP 被暫時封鎖。
