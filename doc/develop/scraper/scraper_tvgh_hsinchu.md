# 臺北榮民總醫院新竹分院 (TVGH_HSINCHU) 爬蟲機制

本文件說明 `app/scrapers/tvgh_hsinchu.py` 中實作的臺北榮民總醫院新竹分院 (TVGH_HSINCHU) 爬蟲運作原理。

## 運作原理與機制

新竹榮總的系統同樣採用傳統 JSP 渲染，爬蟲實作過程大量仰賴純 HTTP GET 請求。與許多其他榮總分院類似，其掛號系統與看診進度都在相同網域 (`webreg.vhct.gov.tw`) 內。本爬蟲完全**不需要**處理 Cookie Session 或 POST，也沒有 AJAX 動態載入，因此是一個相對穩定迅速的爬蟲實作。

## 爬蟲流程與主要 API

### 1. 取得科室清單 (`fetch_departments`)
- **API URL**: `https://webreg.vhct.gov.tw/register/listSection.jsp?type=init`
- **流程**:
  1. GET 請求頁面，尋找帶有 `listDoctor.jsp?section=...` 的 `<a>` 連結。
  2. 透過 Regex 將 `section=` 後面的代碼抓出做為 `dept_code`。
  3. 執行字串清理 (`strip`)，並建立過濾機制 (`skip_keywords`) 排除如「行政」、「教學」、「專案」、「疫苗」等非看診科室。
  4. 使用內部定義的字典 `_categorize_department` 自動將科室歸類到對應的醫療大科別。

### 2. 取得門診表 (`fetch_schedule`)
- **API URL**: `/register/listDoctor.jsp?init=init&section={dept_code}`
- **流程**:
  1. 利用上面取得的科室代碼，請求該科室的網頁清單。
  2. 網站將該科室「未來所有有開診的醫師與日期」以多個隱藏 `<form>` 存在於頁面中。
  3. 爬蟲巡覽所有的 `<form>`，並提取對應的 `<input>` 隱藏欄位：
     - `doctorChineseName` (醫師名稱)
     - `consultDateAD` (看診日期，格式 YYYYMMDD)
     - `doctorNumber` (醫師代碼)
     - `consultNoonFlag` (午別旗標：A/P/N 代表 上/下/夜)
     - `consultRoomLocation` (診間位置)
  4. 直接組合並回傳 `DoctorSlot`。此作法比台中榮總有效率很多，不用一一發送請求給每位醫生。

### 3. 取得即時叫號進度 (`fetch_clinic_progress`)
- **API URL**: `/tiec/OpdProgress1.jsp`
- **流程**:
  1. GET 請求看診進度總表頁面。此頁面會列出全院的各科看診進度，分成上午診、下午診、夜間診多個區塊 (`panel`)。
  2. 爬蟲先透過 `BeautifulSoup` 尋找文字包含「上午診/下午診/夜間診」的 `<span>` 標籤，然後定位到下一個 `div.panel` 作為搜尋目標區塊。
  3. 在該區塊內，尋找所有 class 為 `grid-item` 的 div 節點。
  4. 解析每一個節點內由 `<td>` 包裝的文字 (包含科室、醫生名稱、及目前號碼)。
  5. **比對邏輯**:
     - 優先比對傳入的 `doctor_name` 是否包含在文字中。
     - 若無，則比對 `room` (在此系統中，掛號資料庫將 `room` 視同 `dept_name` 科室名稱) 是否包含在文字中。
  6. 取出找到的目前號碼 (`target_number`)，並回傳 `ClinicProgress`。

## 與 Scheduler / Supabase 的相依性

- **Room 欄位的挪用**: 值得注意的是，此爬蟲在抓取進度時，是優先使用科室名稱 (`dept_name`) 或是醫師名稱匹配。`scheduler` 傳遞過來的 `room` 參數，實際上在 `fetch_clinic_progress` 中被解讀作為 `dept_name` 的搜尋依據使用。
- **簡化的剩餘人數**: 該網站沒有提供「未報到人數」或「目前等候名單」，因此 `calculate_remaining_count` 也是退回到預設的數學相減 `target_number - current_number`。
