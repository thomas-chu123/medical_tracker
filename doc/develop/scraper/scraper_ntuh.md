# 台大醫院新竹分院 (NTUH) 爬蟲機制

本文件說明 `app/scrapers/ntuh.py` 中實作的台大醫院新竹生醫醫院竹北院區 (NTUH_HSINCHU) 爬蟲運作原理。

## 運作原理與機制

NTUH 爬蟲透過 HTTP 請求直接解析 HTML 與 AJAX，由於台大醫院的網站結構複雜且包含多種防止直接解析的動態渲染與屬性隱藏手法，此爬蟲實作了多種**備援解析策略 (Fallback Strategies)**，以確保在結構微調時仍能取到資料。使用了 `BeautifulSoup` 和正則表達式來對付不規則的 DOM 結構。

## 爬蟲流程與主要 API

### 1. 取得科室清單 (`fetch_departments`)
- **API URL**: `/RegShowBlock` (包含多個區塊，如 A: 內科系、B: 外科系、C: 婦兒/其他)
- **流程**:
  1. 向 `RegShowBlock` 發生請求抓取各區塊 (A, B, C) 的 HTML。
  2. 尋找 `<div class="panel-body">` 內的連結 `<a href="/RegDeptSchedule?deptCode={code}&showBlock={block}">`。
  3. 將對應的 `dept_code` 與 `showBlock` (如 A, B, C) 儲存到內部的 `_dept_block_map` 暫存，因為後續查詢班表需要 `showBlock` 參數。

### 2. 取得門診表 (`fetch_schedule`)
- **API URL**: `/RegDeptSchedule` (包含參數 `deptCode`, `vHospCode=T4`, 和 `showBlock`)
- **流程**:
  1. 若不知 `showBlock`，則先打請求動態探測 (暴力測試 A, B, C)，從含有該科別名稱的區塊中找出正確的。
  2. 此頁面是一個龐大的表格或清單，依日期 (`RegDate`) 和時段 (`AmpmCode`) 分組。
  3. **解析策略 (Strategy 1: `_parse_result_div`)**: 找尋 `div.result-div`，解析其 `table` 結構。
  4. **解析策略 (Strategy 2: `_parse_h5_schedule`)**: 如果沒有 `result-div`，則找 `<h5 class="...schedule-title">`，解析其緊跟的列表 `<ul class="doctor-list">`。
  5. 擷取醫生資訊，通常隱藏在按鈕 `<button class="doctor-tag">` 或是 `<div class="doctor-doc">` 內。這一步也包含從 `onclick` 或屬性中透過 Regex `DR_ID_RE` 找出 `drID`。

### 3. 取得即時叫號進度 (`fetch_clinic_progress` / `fetch_today_clinic_list`)
NTUH 查詢進度分為二階段，先查列表取得「動態 Service ID」，再查個案詳細：
- **階段一：今日診間列表 (`DeptLightTable` AJAX POST)**
  1. 請求 `/ClinicCurrentLightNo` 以取得頁面上的隱藏參數 `__RequestVerificationToken`。
  2. 打 POST 到 AJAX endpoint `/DeptLightTable`，帶上 Token、時段 (`AmpmCode`) 和科別 (`DeptCode`)。
  3. 頁面會回傳一堆診間卡片，爬蟲解析出該診間的 `ServiceIDSE` (這是 NTUH 動態生成的追蹤碼)。為避免重複請求，此列表會被**快取 5 分鐘** (`self._cache_lock`)。
- **階段二：查詢特定診間進度 (`ClinicCurrentLightNoDetail`)**
  1. 用上述拿到的 `ServiceIDSE`，請求 `/ClinicCurrentLightNoDetail?ServiceIDSE={sid}`。
  2. 解析頁面上的狀態區塊：
     - `now-number` (目前燈號)
     - `biggest-number` (已叫最大號)
     - `next-number` (預計叫號)
     - `progress-number` (每一位掛號者的報到狀態，如 "3已報到"、"5未報到")
  3. 計算掛號人數 (`registered_count`) 與等待列表 (`waiting_list`)。

## 與 Scheduler / Supabase 的相依性

- **Service ID 的動態性**: 因為進度需要 ServiceIDSE，而這個 ID 無法從排班表 (`fetch_schedule`) 預先得知。所以在 `scheduler.py` 呼叫 `fetch_clinic_progress` 時，爬蟲通常必須先 (或依賴快取) 呼叫 `fetch_today_clinic_list` 來找出對應的 `matched_sid`，才能查到真實看診進度。
- **Waiting Count 提供方式**: NTUH 提供詳細的燈號清單 (`clinic_queue_details`)，`calculate_remaining_count` 會根據清單過濾掉「未報到」的人，回傳實際在現場等待的人數給 `scheduler` 寫入。
- **頻寬控制**: 為了應付台大網頁龐大的 DOM 樹，NTUH 爬蟲內部實作了基於 `dept_code` 的 `_today_clinic_list_cache` 快取機制，防止每追蹤一個該科室的號碼就重新打一次 AJAX 列表請求。
