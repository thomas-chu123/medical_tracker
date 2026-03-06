# TVGH_HSINCHU (臺北榮民總醫院新竹分院) 爬蟲文件

## 概述
TVGH_HSINCHU 爬蟲負責抓取臺北榮民總醫院新竹分院的科別清單、醫師排班表以及即時看診進度。

- **醫院代碼**: `TVGH_HSINCHU`
- **爬蟲類別**: `TvghHsinchuScraper`
- **實作檔案**: `app/scrapers/tvgh_hsinchu.py`

## 爬取邏輯

### 1. 基礎設定
- **Base URL**: `https://webreg.vhct.gov.tw`
- **SSL 驗證**: 停用 (`verify=False`)，因部分醫院憑證較舊。
- **User-Agent**: 模擬瀏覽器 (`Mozilla/5.0 ...`)。

### 2. 科別抓取 (`fetch_departments`)
- **URL**: `/register/listSection.jsp?type=init`
- **方法**: 抓取所有 `listDoctor.jsp?init=init&section=...` 的連結，提取科別名稱與代碼。

### 3. 醫師排班 (`fetch_schedule`)
- **URL**: `/register/listDoctor.jsp?init=init&section={dept_code}`
- **方法**:
  - 此頁面將醫師與時段資訊隱藏在 `form` 的 `hidden` 欄位中。
  - 爬蟲會遍歷所有包含醫師姓名的按鈕，解析其對應的日期、醫師名稱及 `room/period` 參數。

### 4. 即時看診進度 (`fetch_clinic_progress`)
- **URL**: `/tiec/OpdProgress1.jsp`
- **方法**: 抓取表格中的房間號碼、醫師姓名與目前診號。
- **人數估計**: 
  - 由於該分院頁面無詳細候診名單，估計邏輯參考 HMMH (馬偕新竹)。
  - `估計等待人數 = max(0, 掛號號碼 - 目前燈號)`

## 系統註冊
1. 在 `app/scrapers/hospital_registry.py` 的 `HOSPITAL_SCRAPERS` 字典中註冊。
2. 在 `app/config.py` 的 `SUPPORTED_HOSPITALS` 列表加入說明。

## 測試說明
- **單元測試**: `tests/scraper/test_tvgh_hsinchu_scraper.py`
  - 使用 Mock HTML 驗證解析邏輯。
- **API 整合測試**: `tests/api/test_tvgh_api_integration.py`
  - 驗證 Fast API 端點與配置加載。

## 常見問題
- **HTTP 503**: 若醫院服務器過載可能回傳該錯誤，爬蟲已整合 `tenacity` 進行重試。
- **科別代碼變更**: 若院方更改 JSP 參數，需更新 `fetch_departments` 的解析規則。
