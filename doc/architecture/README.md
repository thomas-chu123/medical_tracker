# 系統架構說明文件

## 概述

本系統採用微服務架構的設計模式，主要基於 FastAPI 作為後端核心框架，並充分利用異步（Async）處理來提升高併發量爬蟲與排程作業的效能。系統核心業務包含醫療門診資訊蒐集、狀態追蹤及自動推播通知。

## 系統元件與目錄結構

*   **`app/api/` (API 層)**: 
    *   負責所有 HTTP 請求與回應處理。
    *   切割為獨立 router，如使用者 (users)、醫院服務 (hospitals)、統計資料 (stats)、追蹤設定 (tracking)、系統管理 (admin) 及 webhook 接口。
*   **`app/core/` (核心設置層)**:
    *   包含系統共用機制，如日誌紀錄 (logger.py) 以及共用環境配置檔 (config.py)。
*   **`app/models/` (資料模型層)**:
    *   主要定義系統中使用的 Pydantic Models，供 API 接收參數驗證與資料轉換使用。
*   **`app/services/` (商業邏輯層)**:
    *   抽離核心功能邏輯與第三方串接服務。
    *   包含 Email 發送、LINE 訊息整合發送（`line_service.py`、`line_message_api.py`）、通知判斷處理 (`notification.py`) 以及資料庫寫入服務。
*   **`app/scrapers/` (網頁爬蟲層)**:
    *   專責將不同醫療院所的診間看診進度進行解析，分為基礎爬蟲物件 (`base.py`) 以及客製化的各大醫院實現。
*   **`app/scheduler.py` (排程管理服務)**:
    *   基於 APScheduler 將異步爬蟲、通知、與資料整併作業進行例行性背景作業。

## 軟體架構模式

*   **無狀態 (Stateless)**: API 服務為無狀態設計，所有持久化相關狀態統一由 Database (Supabase) 處理。
*   **工作管理 (Background Tasks)**: 針對高耗時爬蟲採取單一獨立背景線程運作或 Async 協程調度以防阻塞 API 主線程。

## 系統安全設計

*   跨來源資源共用 (CORS) 進行管控。
*   所有的組態檔（Token、密碼及 URL）接由環境變數 `.env` 動態載入，不僅限於程式碼當中。

## 系統數據流與通訊架構

### 完整請求流程圖
```
┌──────────────────┐
│  前端應用 (SPA)   │
│  (static/js/)    │
└────────┬─────────┘
         │ HTTP 請求
         ▼
┌──────────────────────────┐
│  FastAPI API 層          │ ──────────┐
│  (app/api/)              │           │
│ - Authorization          │           │
│ - Users, Hospitals       │           │ JWT 驗證、
│ - Tracking, Stats        │           │ 資料驗證
│ - Admin, Webhooks        │           │
└────────┬─────────────────┘ ──────────┘
         │ Service 呼叫
         ▼
┌──────────────────────────┐
│  商業邏輯層 (Services)   │
│  (app/services/)         │
│ - notification.py        │──────┐
│ - line_service.py        │      │ 決定通知策略
│ - email_service.py       │      │
│ - data_writer.py         │──────┤
└────────┬─────────────────┘      │ 批量資料寫入
         │                        │
         ▼                        ▼
┌──────────────────────────┐  ┌──────────────────┐
│  排程服務 (APScheduler)   │  │  第三方服務       │
│  (app/scheduler.py)      │  │ - LINE API       │
│ 每 3 分鐘執行：           │  │ - Email SMTP     │
│ - run_tracked_appt()     │  │ - 通知推送       │
│ - check_and_notify()     │  └──────────────────┘
└────────┬─────────────────┘
         │
    ┌────┴──────────────────┐
    │                       │
    ▼                       ▼
┌──────────────────┐  ┌──────────────────┐
│  爬蟲層           │  │  資料庫 (Supabase)│
│  (app/scrapers/) │  │  (PostgreSQL)    │
│ - BaseScraper    │  │ - Users          │
│ - CMUHScraper    │  │ - Hospitals      │
│ - NTUHScraper    │  │ - Snapshots      │
│ - ...            │  │ - Tracking Subs  │
└────────┬─────────┘  │ - Notifications  │
         │            └──────────────────┘
         ▼
┌──────────────────────────┐
│  醫院網站                 │
│  (目標爬蟲網址)          │
│ - CMUH                  │
│ - NTUH Hsinchu          │
│ - ...                   │
└──────────────────────────┘
```

### 排程任務流程圖 (Scheduler)
```
┌────────────────────────────────────────────────────┐
│  APScheduler 主迴圈（系統啟動時初始化）           │
└────────────────────┬───────────────────────────────┘
                     │
        ┌────────────┼────────────┐
        │            │            │
        ▼            ▼            ▼
   ┌─────────┐  ┌──────────┐  ┌─────────────┐
   │  時間   │  │   時間   │  │  每 N 分鐘  │
   │ 00:00   │  │  08:00   │  │   一次      │
   │ UTC+8   │  │ UTC+8    │  │  (預設 3')  │
   └────┬────┘  └────┬─────┘  └──────┬──────┘
        │            │               │
        ▼            ▼               ▼
   Master Data   Morning Sync   Tracked Appt
   Sync Full     Snapshot       Progress Check
   
   │              │              │
   └──────┬───────┘              │
          │                      ▼
          ▼                   check_and_notify()
   run_cmuh_master_data()         │
   run_ntuh_master_data()    ┌────┴────┐
   ...                       │          │
                        ┌────▼────┐    │
                        │ Remaining│   │
                        │ Count    │   │
                        │ ≤ 20/10/5│   │
                        └────┬─────┘   │
                             │         │
                        YES  │    NO   │
                        ┌────▼─────────▼──┐
                        │ send_notification│
                        │ (email/LINE)     │
                        └──────────────────┘
```

## 非同步處理與並行機制

### AsyncIO 使用場景
```python
# 爬蟲並行執行
async def run_tracked_appointments():
    """同時爬取多個醫師的最新進度"""
    tasks = [
        scraper.fetch_clinic_progress(doc_id) 
        for doc_id in tracked_doctors
    ]
    results = await asyncio.gather(*tasks)  # 並行等候
```

### 線程池與 Supabase 同步呼叫
```python
# Supabase 為 sync 客戶端，需用 asyncio.to_thread 包裹
async def batch_upsert_snapshots(snapshots: list):
    await asyncio.to_thread(
        lambda: supabase.table('appointment_snapshots')
            .upsert(snapshots)
            .execute()
    )
```

## 層間依賴與通訊

### API 層 → Services 層
```python
# app/api/tracking.py
from app.services.notification import check_and_notify

@router.get("/tracking/status/{doctor_id}")
async def get_status(doctor_id: str):
    # 調用 Service 層檢查通知
    eta = await check_and_notify(doctor_id)
    return {"eta": eta}
```

### Services 層 → Scrapers 層
```python
# app/services/notification.py
from app.scrapers.registry import get_scraper

async def check_and_notify():
    scraper = get_scraper(hospital_code)
    progress = await scraper.fetch_clinic_progress(...)
    # 判斷是否需通知
```

### Services 層 → Database
```python
# app/services/data_writer.py
async def write_snapshot(snapshot_data):
    await asyncio.to_thread(
        lambda: supabase.table('appointment_snapshots')
            .upsert(snapshot_data)
            .execute()
    )
```

## 時段感知與快照寫入策略

系統根據台灣時間自動判斷診間是否開始，決定是否寫入即時進度：

| 時段 | 開始時間 | 結束時間 | 即時進度寫入條件 |
|------|--------|--------|-----------------|
| 上午 | 08:30 | 16:45 | 當前時間 ≥ 08:30 且已追蹤 |
| 下午 | 13:30 | 21:30 | 當前時間 ≥ 13:30 且已追蹤 |
| 晚上 | 18:00 | 02:00* | 當前時間 ≥ 18:00 且已追蹤 |

*晚上時段跨越午夜，使用 `schedule_end` 時間比較而非日期比較

## 擴展性設計

### 新增醫院爬蟲步驟

1. **在 `app/scrapers/` 建立新爬蟲類別**
```python
# app/scrapers/new_hospital.py
from app.scrapers.base import BaseScraper

class NewHospitalScraper(BaseScraper):
    HOSPITAL_CODE = "new_hospital"
    
    async def fetch_departments(self) -> List[DepartmentData]:
        # 實作...
        pass
    
    async def fetch_schedule(self, dept_code: str) -> List[DoctorSlot]:
        # 實作...
        pass
    
    async def fetch_clinic_progress(self, room: str, period: str) -> Optional[ClinicProgress]:
        # 實作...
        pass
```

2. **在 `app/scheduler.py` 的排程函式中註冊爬蟲**
```python
async def run_cmuh_master_data():
    scrapers = [
        CMUHScraper(),
        CMUHHsinchuScraper(),
        NewHospitalScraper(),  # 新增
    ]
    # 執行爬蟲...
```

3. **在 Supabase 的 `hospitals` 表中新增記錄**
```sql
INSERT INTO hospitals (hospital_code, hospital_name, location)
VALUES ('new_hospital', '新醫院名稱', '台北市');
```
