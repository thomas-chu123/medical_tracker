# 台中榮民總醫院 (TVGH_TAICHUNG) 爬蟲機制

本文件說明 `app/scrapers/tvgh_taichung.py` 中實作的台中榮民總醫院 (TVGH_TAICHUNG) 爬蟲運作原理。

## 運作原理與機制

台中榮總的掛號網頁與看診進度網頁分別位於不同的主網域下。掛號系統使用 JSP 架構 (`register.vghtc.gov.tw`)，而看診進度則提供在官網的 API 頁面 (`www.vghtc.gov.tw/APIPage`)。爬蟲主要使用純 HTTP GET 請求搭配 `BeautifulSoup` 解析 HTML 節點。

## 爬蟲流程與主要 API

### 1. 取得科室清單 (`fetch_departments`)
- **API URL**: `https://register.vghtc.gov.tw/register/listSection.jsp`
- **流程**:
  1. GET 請求頁面，尋找所有的表格列 `<tr>`。
  2. 透過 `<th>` 標籤找出科室的大分類 (如：內科部、外科部)。
  3. 透過 `<a>` 連結 (包含 `listDoctor.jsp?section=...`) 中利用 Regex 解析出 `dept_code` (科室代碼) 與名稱。
  4. 利用字典進行去重並建立 `DepartmentData` 清單。

### 2. 取得門診表 (`fetch_schedule`)
- **API URL**: `/register/listDoctor.jsp` 與 `/register/doctor_schedule.jsp`
- **流程**:
  1. 先向 `listDoctor.jsp` 送出科室代碼，取得該科室下所有的醫師名單。醫師的資訊藏在 `<a onclick="showDoc(...)">` 或 `<div class="doc" onclick="showDoc(...)">`。
  2. 提取出每位醫生的 `drno` 與 `drname`。
  3. 利用 `asyncio.gather` 並行向 `doctor_schedule.jsp` 發送每位醫師的班表請求。
  4. 解析回傳頁面內的隱藏 `<form>`，提取出看診日期 (`consultDateAD`)、診間 (`consultRoom`)、午別 (`consultNoonFlag`: A/P/N/E)，並確認是否有額滿或已掛號人數的文字。

### 3. 取得即時叫號進度 (`fetch_clinic_progress`)
- **API URL**: `https://www.vghtc.gov.tw/APIPage/OutpatientProcess2` (與 `OutpatientProcess3`)
- **流程**:
  1. 官網的看診進度 API，根據科室代碼 (`SECTION_ID`) 直接抓取。如果科室代碼為 `WBC` (健兒門診)，則優先嘗試 `OutpatientProcess3`。
  2. 如果有提供 `doctor_name` 且在主科別找不到，爬蟲會有備援機制去 `WBC` 科別搜尋，因為許多兒科醫師也會在那邊看診。
  3. 頁面回傳的是一個完整的 HTML `<table>`，每列包含：時段、診間、醫師、掛號人數、目前叫號、已報到待看診人次 等 8 個欄位。
  4. 爬蟲會比對指定的「時段」、「醫師名稱」或「診間號碼」，找出符合的該列。
  5. 將解析出的目前序號作為 `current_number` 回傳。

## 與 Scheduler / Supabase 的相依性

- **沒有精確的 Wait Count**: 雖然 API 頁面有提供「已報到待看診人次」，但此腳本中的邏輯有抓取但未將其直接當成看診進度的唯一參考指標。`calculate_remaining_count` 方法仍沿用傳統的 `target_number - current_number` 簡易估算法。
- **並行請求**: `fetch_schedule` 中採用了 `asyncio.gather` 來大量獲取各個醫生的班表，這會對伺服器產生一定程度的併發連接，如果有遇到 block，可能需要加入 `Semaphore` 限制。
