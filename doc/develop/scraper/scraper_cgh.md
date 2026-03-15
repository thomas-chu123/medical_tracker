# 國泰綜合醫院新竹分院 (CGH) 爬蟲機制

本文件說明 `app/scrapers/cgh_hsinchu.py` 中實作的國泰綜合醫院新竹分院 (CGH_HSINCHU) 爬蟲運作原理。

## 運作原理與機制

CGH 爬蟲必須處理早期 JSP 網站常見的「隱藏表單 POST」架構與「Session 綁定」。爬蟲沒有使用 AJAX 選取，而是必須解析 HTML 中的 Javascript `onclick` 操作，提取表單參數，並依序送出連串的 POST 請求來完成操作。

## 爬蟲流程與主要 API

### 1. 取得科室清單 (`fetch_departments`)
- **API URL**: `/tw/reg/main_01.jsp?area=3` (area=3 代表新竹分院)
- **流程**:
  1. 使用 GET 請求頁面。
  2. 尋找所有隱藏表單 `<form name="f1" ...>`，包含內建的 `<input name="dept" value="...">`。
  3. 雖然一般使用者是點擊 `<a href="javascript:document.f1.submit();">`，爬蟲只需抓出所有的隱藏 `<input>` value 與對應的科室名稱即可。

### 2. 取得門診表 (`fetch_schedule`)
CGH 的看診表查詢極其複雜，分布在多個步驟。
- **流程**:
  1. **建立 Session**: 必須先 GET `/tw/reg/main.jsp` 來取得 Tomcat 的 `JSESSIONID` cookie。沒有這個 Cookie 後續的 POST 都會失敗。
  2. **取得週班表**: POST 到 `/tw/reg/main_01.jsp` (帶有 `area`, `dept`, `deptn`) 來取得一個以星期為單位的表格。
  3. **解析星期表格**: 表格內的醫生排班是以按鈕形式存在，附有 `javascript:sub(document.sec10111, '07931/醫師名', '3', '000')`。
     - Regex 解析這個字串，並找到對應的 `<form name="sec10111">` 提取隱藏欄位 (如 `week`, `room`, `sec`)。
  4. **獲取實際看診日期 (`main_02.jsp`)**: 上述只拿到「這位醫生每週 X 哪個時段有看診」。必須再 POST 一次資料 (帶入 `doctor`, `drn`, `week`) 到 `/tw/reg/main_02.jsp`。
  5. 該頁面會回傳這位醫生未來幾週「實際有開診的日期」。日期格式為民國年 `115.03.16`，經過自訂的 `_roc_date_to_iso` 解析為 `2026-03-16`。

### 3. 取得即時叫號進度 (`fetch_clinic_progress`)
- **API URL**: `/tw/reg/RealTimeTable.jsp`
- **流程**:
  1. 再次 GET 首頁建立/更新 Session。
  2. POST 包含 `hosarea=3`, `sec={時段}`, `_sec={時段}`, `room={診間}` 的表單。
  3. 回傳頁面是個純文字/簡單表格。爬取主要資訊：
     - `目前看診序號：(\d+)`
     - `尚未就診病人號碼：` (如果有的話，會接一連串 `<td>` 放號碼，或者散佈在文字中)
  4. **數據計算**: 從尚未就診病人清單的最後一個號碼，推估出出 `total_quota` (總掛號數)，與 `registered_count` (尚未看診的人數)。
  5. **狀態判斷**: 沒有看到號碼時，檢查頁面包含的字詞 (如「已結束看診」、「非看診時段」等) 來定義看診狀態。

## 與 Scheduler / Supabase 的相依性

- **民國日期轉換**: 由於傳回的排程日期是 `115.03.16` 或 `1150316` 格式，此爬蟲自帶了詳細的民國轉西元驗證邏輯 `_roc_date_to_iso`。它直接決定了存入 `appointment_snapshots` 時主鍵之一 (`session_date`) 的正確性。
- **Waiting Count 計算**: CGH 有給出「尚未就診號碼」，`scheduler.py` 估算看診速度時會利用這個清單長度。
- **防呆過濾 (`_categorize_department`)**: 爬蟲已經自帶一些過濾關鍵字 (`疫苗`, `額滿`, `代診`, `COVID`) 不當作一般科室存入資料庫，以保持系統乾淨。
