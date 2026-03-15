# 中國醫藥大學附設醫院 (CMUH) 爬蟲機制

本文件說明 `app/scrapers/cmuh.py` 中實作的中國醫藥大學附設醫院 (CMUH_TAICHUNG) 及新竹附醫 (CMUH_HSINCHU) 的爬蟲運作原理。

## 運作原理與機制

CMUH 爬蟲使用 `httpx.AsyncClient` 模擬瀏覽器發送 HTTP GET/POST 請求，並透過 `BeautifulSoup` (lxml 解析器) 解析回傳的 HTML 內容。由於部分後端 CGI 程式 (如進度查詢) 會回傳 `Big5` (CP950) 編碼的內容，因此在解析時有特別處理解碼。

中國醫的網站架構分為：
1. **主網頁前端**: 顯示科室分類。
2. **CGI 後端**: 處理實際的排班表與看診進度查詢 (`https://appointment.cmuh.org.tw/cgi-bin/`)。

## 爬蟲流程與主要 API

### 1. 取得科室清單 (`fetch_departments`)
- **API URL**: `/OnlineAppointment/AppointmentByDivision?flag=first`
- **流程**: 請求主網站的科屬分類頁面，解析 `onlinedivision_box` 區塊。
- **資料提取**: 透過 Regex `table=([A-Za-z0-9]+)` 從連結中提取 `dept_code`。
- **新竹附醫特例**: `CMUHHsinchuScraper` 繼承並覆寫此方法，手動將科室名稱對應至 `category_map`，以補足新竹附醫網頁本身無明確分類的缺點。

### 2. 取得門診表 (`fetch_schedule`)
- **API URL**: `/OnlineAppointment/DymSchedule?table={code}&flag=first`
- **流程**: 
  1. 請求上述 URL 獲取該科室的所有醫生代號 (`DocNo`)。
  2. 平行發送請求 (最大併發 5) 到 CGI 後端 `/reg52.cgi` 查詢每位醫生的詳細門診表。
- **CGI API**: `/cgi-bin/reg52.cgi?DocNo=D{doc_no}&Docname={name}`
  - CGI 頁面會回傳一個包含時段（上午、下午、晚上）與一週日期的表格。
  - 使用 Regex `(.*診)` 或 `\d+` 取出診間代號。
  - 提取日期 (11x/xx/xx 民國年轉西元年)、已掛號人數、以及是否「額滿」。

### 3. 取得即時叫號進度 (`fetch_clinic_progress`)
- **API URL**: `/cgi-bin/reg64.cgi` (新竹附醫為 `reg64x.cgi`)
- **參數**: `TimeCode` (1=上午, 2=下午, 3=晚上), `CliRoom` (診間號碼)
- **流程**:
  1. 向 CGI API 發送 GET 請求，並強制以 `Big5` 解碼回傳的 HTML。
  2. 使用正則表達式尋找 `目前診號 <strong>104</strong>` 或類似格式以提取 `current_number`。
  3. 解析頁面下方的看診清單表格 (包含各號碼及其狀態如「未看診」、「完成」)。
  4. 判斷是否有「看診完畢」、「未開診」等全域狀態。
- **輸出**: 回傳 `ClinicProgress` 物件，包含總名額、已掛號數、目前號碼、以及完整的 `clinic_queue_details` 排隊明細。

### 4. 剩餘人數計算 (`calculate_remaining_count`)
- CMUH 頁面會列出所有掛號者的狀態。
- 計算方式：遍歷 `clinic_queue_details`，統計號碼介於 `current_number` 與 `target_number` 之間，且狀態 **不等於** "完成" 的人數。這能精準扣除過號或已退掛的人數。

## 與 Scheduler / Supabase 的相依性

- **非同步支援**: CMUH 爬蟲高度仰賴 `httpx` 的非同步請求與 `asyncio.gather` 併發處理。為避免被阻擋，部分環節有加入 `asyncio.sleep(0.5)` ~ `sleep(3.0)` 的延遲。
- **資料對應**: 抓取到的 `DoctorSlot` 會被 `scheduler.py` 透過 `upsert_doctor` 與 `batch_insert_snapshots` 寫入 Supabase。由於 CMUH CGI 不直接提供 `total_quota`，因此排班表階段的 `total_quota` 為 None；這項數據是在 `fetch_clinic_progress` 階段透過解析號碼表的最大值來補齊。
- **狀態判定**: 因為 CMUH 的燈號有時可能會與狀態衝突（例如有燈號但其實已「看診完畢」），`scheduler.py` 會綜合 `current_number` 與 `status` 寫入 `appointment_snapshots` 中最終的狀態。
