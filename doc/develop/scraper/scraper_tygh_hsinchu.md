# 東元綜合醫院 (TYGH) 爬蟲機制

本文件說明 `app/scrapers/tygh_hsinchu.py` 中實作的東元綜合醫院 (TYGH_HSINCHU) 爬蟲運作原理。

## 運作原理與機制

東元綜合醫院的系統 (`w3.tyh.com.tw`) 使用基於 ASP.NET (副檔名為 `.aspx`) 的網域。爬蟲採用純 HTTP GET 方法解析，但因為系統結構規劃，必須依照 `科室清單` -> `科室下醫生清單` -> `單一醫生排班清單` 的串列邏輯發送請求。爬蟲內建了連線數 `Semaphore(5)` 控制以避免並行請求過度轟炸伺服器。

## 爬蟲流程與主要 API

### 1. 取得科室清單 (`fetch_departments`)
- **API URL**: `/WebRegDept.aspx`
- **流程**:
  1. 請求主頁，找出具有 `href` 屬性為 `WebRegList_Dept.aspx?d={dept_code}` 的超連結 `<a>`。
  2. 利用 Regex 擷取出目標的科室代碼 (`d` 參數)。
  3. 過濾掉包含特殊關鍵字 (如：疫苗、教學、戒菸等) 的非一般看診科室。
  4. 利用自帶字典 `_categorize_department` 歸類如「內科系」、「外科系」。

### 2. 取得門診表 (`fetch_schedule`)
東元醫院的班表須分兩層獲取：
- **第一級 API URL**: `/WebRegList_Dept.aspx?d={dept_code}`
  - 首先請求特定科室的網頁，列出底下的所有醫師。醫師的連結形式如 `WebRegList_Doct.aspx?dn=0709&d=07`。
  - 將不重複的醫生代碼 (`dn`) 與醫師姓名記錄下來。
- **第二級 API URL**: `/WebRegList_Doct.aspx?dn={doc_no}&d={dept_code}`
  - 將所有紀錄的醫師交給 `asyncio.Semaphore(5)` 並行處理。
  - 第二級網頁會顯示這位醫師未來幾週有開診的時段。資料藏在特定的 Radio Button 隱藏數值內：`<input name="RadioDoct" value="0A1150309A1A07A1">`。
  - 爬蟲會拆解這個值：第一部分為民國看診日期 (`1150309` 轉西元 `2026-03-09`)，並解析後面的文字節點判斷「上午/下午/夜間」與「是否已額滿/停診」。
  - 同時也支援解析字串中的 `已掛號:X人` 欄位並存入資料庫。

### 3. 取得即時叫號進度 (`fetch_clinic_progress`)
- **API URL**: `/MainWebProcess.aspx`
- **流程**:
  1. 此頁面為全院當前的一覽表，不需要額外的 GET 參數。
  2. 若頁面文案包含「目前非轉檔時段」，則代表所有門診皆處於關閉狀態，直接回傳 `未開診` 狀態。
  3. **新舊模板通用解析**: 
     - **新版 (List Layout)**: 尋找所有的 `<li class="number-light-box">`。其中分別定義了 `.room` (診間號)、`.name` (醫師名稱)、`.number` (目前號碼) 與包裹時段的 span。根據 `period` (1=上午, 2=下午, 3=晚上) 驗證時段是否符合。
     - **舊版 (Table Layout)**: 如果上一步失敗，爬蟲會找尋所有的 `<table><tr>` 列，解析三個欄位：`dept_name`、`doc_name`、`number_str`。舊版配置往往把科別名稱放在本來診間的位置。
  4. **比對邏輯**: 兩種狀況下，都會優先利用傳入的 `doctor_name` 是否存在文案中，或者 `room` 是否匹配，來決定資料列是否正確。取出後即回傳 `ClinicProgress`。

## 與 Scheduler / Supabase 的相依性

- **Semaphore 節流**: 東元系統對連線數目可能有潛在防護，在獲取大量醫師班表的爬蟲函數 (`fetch_schedule`) 內部採用了 `Semaphore(5)` 來實現並發控制，避免高頻阻斷，也保證 Scheduler 定時啟動時能穩定收集。
- **待看診人數缺失**: 此系統僅提供目前叫號 (`number_str`)，無「尚未看診名單」等進階資料，因此在 Scheduler 中的預估診療等待時間無法運用 `waiting_count` 演算法，而是退回簡單的 `target_number - current_number` 運算。
