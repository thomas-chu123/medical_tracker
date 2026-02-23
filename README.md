# 台灣醫療門診追蹤系統

自動蒐集台灣各大醫院的門診掛號人數與目前叫號進度，並在門診即將輪到您時，以 **Email** 或 **LINE** 即時通知。

## 功能特色

- 🏥 **多醫院支援**：初期以中國醫藥大學附設醫院（CMUH）為範例，架構可擴充至全台醫療院所
- 📊 **每5分鐘自動更新**：掛號人數、剩餘號碼、門診進度
- 🔔 **智慧通知**：在距您還剩 20 / 10 / 5 號時，以 Email 或 LINE 提醒
- 👤 **使用者管理**：JWT 認證，個人化追蹤清單
- 📡 **REST API**：完整 FastAPI + OpenAPI (Swagger) 文件

## 快速開始

### 1. 環境需求

- Python 3.11+
- Supabase 帳號（已預設設定）

### 2. 安裝

```bash
cd medial_help
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. 環境變數

複製並編輯 `.env`：

```bash
cp .env.example .env
# 編輯 .env 填入 SMTP 帳號密碼
```

### 4. 建立 Supabase 資料庫

在 [Supabase SQL Editor](https://supabase.com/dashboard) 執行：

```
supabase/migrations/001_initial_schema.sql
```

### 5. 啟動服務

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 6. 查看 API 文件

開啟瀏覽器：[http://localhost:8000/docs](http://localhost:8000/docs)

---

## 爬蟲與排程優化 (2024/02)

為提升系統穩定性與資料準確度，近期進行了以下重大優化：

- 🚀 **併發爬取優化**：Scheduler 現在會併發處理多個醫院（如中國醫本院與新竹分院），提升資料更新效率。
- 🛡️ **友善爬蟲行為**：在科室爬取間加入 1.0s ~ 3.0s 的隨機延遲，避免造成醫院伺服器負擔並降低被封鎖風險。
- ⏱️ **時段感應追蹤**：
    - 根據門診時段（上午、下午、晚上）自動切換追蹤模式。
    - 僅在開診時間內（上午 08:00、下午 13:00、晚上 18:00 後）抓取即時進度。
    - 非開診時段或未來日期則顯示凌晨快照資料，減少無效網路請求。
- 🔢 **資料定義標準化**：統一「診間燈號」、「總號（最大掛號號碼）」與「掛號人數」的定義，確保前端顯示正確無誤。

## 專案結構

```
medial_help/
├── app/
│   ├── main.py              # FastAPI 入口 + 排程啟動
│   ├── config.py            # 環境變數設定
│   ├── database.py          # Supabase 連線
│   ├── auth.py              # JWT 驗證
│   ├── scheduler.py         # APScheduler 定時任務
│   ├── api/                 # FastAPI 路由
│   │   ├── auth.py          # 登入/註冊
│   │   ├── users.py         # 使用者管理
│   │   ├── hospitals.py     # 醫院/科室/醫師
│   │   └── tracking.py      # 追蹤訂閱 CRUD
│   ├── models/              # Pydantic 資料模型
│   ├── scrapers/
│   │   ├── base.py          # 爬蟲基礎介面
│   │   └── cmuh.py          # CMUH 爬蟲
│   └── services/
│       ├── data_writer.py   # Supabase 寫入
│       ├── notification.py  # 通知觸發邏輯
│       ├── email_service.py # SMTP Email
│       └── line_service.py  # LINE Notify
├── supabase/
│   └── migrations/001_initial_schema.sql
├── tests/
├── .env
├── .env.example
└── requirements.txt
```

## API 端點一覽

| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | /api/auth/register | 使用者註冊 |
| POST | /api/auth/login | 登入，取得 JWT |
| GET | /api/hospitals | 醫院清單 |
| GET | /api/hospitals/{id}/departments | 科室清單 |
| GET | /api/departments/{id}/doctors | 醫師清單 |
| GET | /api/doctors/{id}/latest | 最新掛號快照 |
| GET | /api/tracking | 我的追蹤清單 |
| POST | /api/tracking | 新增追蹤 |
| DELETE | /api/tracking/{id} | 刪除追蹤 |
| POST | /api/admin/scrape-now | 手動觸發爬蟲（測試用）|

## LINE Notify 設定

1. 前往 [LINE Notify](https://notify-bot.line.me/zh_TW/) → 登入 → 發行權杖
2. 複製 Token，至個人設定頁面填入
3. 在追蹤訂閱設定中開啟「LINE 通知」

## 未來擴充計畫

- **Phase 2**：加入台大醫院、榮總、長庚、馬偕等
- **Phase 3**：門診速度圖表（Chart.js）、等待時間預測
- **Phase 4**：「最容易掛到號」智慧推薦

---

> ⚠️ 本系統以爬蟲存取醫院網站，使用前請確認相關服務條款。
