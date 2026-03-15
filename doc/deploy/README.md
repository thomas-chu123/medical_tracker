# 系統部署與環境建置指南

## 環境概述

此系統設計為現代化的 ASGI FastAPI 應用程式。我們建議使用具備 `uvicorn` 或類似 ASGI Server 的平台進行後端服務容器化部署 (例如使用 Docker)。

## 環境變數完整清單

| 變數名稱 | 必填 | 類型 | 說明 | 範例值 |
|---------|------|------|------|-------|
| `SUPABASE_URL` | ✅ | String | Supabase 專案 URL | `https://xxxxx.supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY` | ✅ | String | Supabase Service Role Key（含全限權限） | `eyJhbGc...` |
| `SUPABASE_ANON_KEY` | ✅ | String | Supabase Anonymous Key（前端用） | `eyJhbGc...` |
| `SECRET_KEY` | ✅ | String | JWT 簽名密鑰（最少 32 個字元） | `your-super-secret-key-min-32-chars` |
| `ALGORITHM` | ❌ | String | JWT 演算法 | `HS256` (預設) |
| `SMTP_HOST` | ❌ | String | Email SMTP 伺服器 | `smtp.gmail.com` |
| `SMTP_PORT` | ❌ | Integer | SMTP 埠號 | `587` |
| `SMTP_USER` | ❌ | String | SMTP 帳號 | `your-email@gmail.com` |
| `SMTP_PASSWORD` | ❌ | String | SMTP 密碼或應用密碼 | `app-specific-password` |
| `SMTP_FROM` | ❌ | String | Email 寄件人 | `noreply@medicaltrack.com` |
| `SMTP_FROM_NAME` | ❌ | String | Email 寄件人名稱 | `門診追蹤系統` |
| `LINE_CHANNEL_ACCESS_TOKEN` | ❌ | String | LINE Messaging API 頻道存取令牌 | `U1234567890abcdef...` |
| `LINE_CHANNEL_SECRET` | ❌ | String | LINE Messaging API 頻道密鑰 | `abcdef1234567890...` |
| `SCRAPE_INTERVAL_MINUTES` | ❌ | Integer | 爬蟲執行間隔（分鐘） | `3` (預設) |
| `LOG_LEVEL` | ❌ | String | 日誌等級 | `INFO` (預設，可用 DEBUG, WARNING, ERROR) |

### 環境變數設定範例 (.env 檔)
```bash
# Supabase
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGc...
SUPABASE_ANON_KEY=eyJhbGc...

# JWT
SECRET_KEY=your-super-secret-key-min-32-chars-please-change-this
ALGORITHM=HS256

# Email (Gmail 範例)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=app-specific-password
SMTP_FROM=noreply@medicaltrack.com
SMTP_FROM_NAME=門診追蹤系統

# LINE Messaging API
LINE_CHANNEL_ACCESS_TOKEN=U1234567890abcdef...
LINE_CHANNEL_SECRET=abcdef1234567890...

# 排程與日誌
SCRAPE_INTERVAL_MINUTES=3
LOG_LEVEL=INFO
```

## 測試環境與 Docker 部署

### 本地開發啟動

```bash
# 1. 建立虛擬環境
python3 -m venv venv
source venv/bin/activate  # Unix/Mac
# 或 venv\Scripts\activate  # Windows

# 2. 安裝依賴
pip install -r requirements.txt

# 3. 建立 .env 檔（複製 .env.example 並填入實際值）
cp .env.example .env

# 4. 啟動開發伺服器
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Docker 容器化部署

**Dockerfile** (專案根目錄)
```dockerfile
FROM python:3.12-slim

WORKDIR /app

# 安裝依賴
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製應用程式
COPY app ./app
COPY static ./static

# 暴露埠號
EXPOSE 8000

# 啟動應用
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**docker-compose.yml** (用於本地開發或完整棧)
```yaml
version: '3.8'

services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      SUPABASE_URL: ${SUPABASE_URL}
      SUPABASE_SERVICE_ROLE_KEY: ${SUPABASE_SERVICE_ROLE_KEY}
      SUPABASE_ANON_KEY: ${SUPABASE_ANON_KEY}
      SECRET_KEY: ${SECRET_KEY}
      SMTP_HOST: ${SMTP_HOST}
      SMTP_PORT: ${SMTP_PORT}
      SMTP_USER: ${SMTP_USER}
      SMTP_PASSWORD: ${SMTP_PASSWORD}
      SMTP_FROM: ${SMTP_FROM}
      LINE_CHANNEL_ACCESS_TOKEN: ${LINE_CHANNEL_ACCESS_TOKEN}
      LINE_CHANNEL_SECRET: ${LINE_CHANNEL_SECRET}
    volumes:
      - ./app:/app/app
      - ./static:/app/static
    command: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**啟動 Docker**
```bash
# 建置映像
docker build -t medical-track:latest .

# 執行容器
docker run -p 8000:8000 \
  -e SUPABASE_URL=your_url \
  -e SUPABASE_SERVICE_ROLE_KEY=your_key \
  medical-track:latest

# 或使用 docker-compose
docker-compose up -d
```

### 常見部署平台

#### Heroku 部署
1. **建立 Procfile**：
```
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
release: python -m app.scheduler
```

2. **設定環境變數**：
```bash
heroku config:set SUPABASE_URL=your_url
heroku config:set SUPABASE_SERVICE_ROLE_KEY=your_key
# ... 其他變數
```

3. **部署**：
```bash
git push heroku main
```

#### Railway 部署
1. 連接 GitHub 倉庫
2. 在 Dashboard 中設定環境變數
3. 自動部署

#### Render 部署
1. 建立新 Web Service
2. 連接 GitHub
3. 設定啟動命令：`uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. 設定環境變數

## 健康檢查與監控

### 健康檢查端點
```bash
# 檢查 API 是否運行
curl http://localhost:8000/api/health

# 回應 (200 OK)
{
  "status": "healthy",
  "timestamp": "2025-01-15T10:30:00+08:00"
}
```

### 日誌查看
```bash
# 本地開發
tail -f app.log

# Docker 容器
docker logs -f <container_id>

# 搜尋特定錯誤
grep "ERROR" app.log
```

## 常見部署問題與排除

| 問題 | 症狀 | 解決方式 |
|------|------|--------|
| **連線 Supabase 失敗** | `ConnectionError: Failed to connect to Supabase` | 檢查 `SUPABASE_URL`、`SUPABASE_SERVICE_ROLE_KEY` 是否正確；檢查網路連線 |
| **JWT 簽名錯誤** | `TokenDecodeError: Signature verification failed` | 確認 `SECRET_KEY` 在本地與伺服器一致；重新生成 Token |
| **SMTP 認證失敗** | `SMTPAuthenticationError: (535, b'5.7.8 Username and password not accepted')` | 確認 Gmail 使用應用密碼而非普通密碼；確認 SMTP_USER 與 SMTP_PASSWORD 一致 |
| **爬蟲超時** | `Timeout: Request exceeded N seconds` | 增加爬蟲超時時間；檢查目標醫院網站是否可達；考慮使用代理 IP |
| **記憶體溢位** | `MemoryError: Tracker server killed due to high memory usage` | 減少並行爬蟲數；增加伺服器記憶體；定期清理舊快照資料 |
| **排程任務未執行** | 爬蟲未在預定時間運行 | 檢查 `APScheduler` 是否正確啟動；檢查時區設定是否為 UTC+8；查看應用日誌 |

## 生產環境檢查清單

部署到生產環境前，請確認以下事項：

- [ ] 所有環境變數已設定（尤其是 `SECRET_KEY` 為強密碼）
- [ ] 資料庫備份已設定（Supabase Point-in-time Recovery）
- [ ] SSL/TLS 憑證已安裝（HTTPS 強制）
- [ ] 監控與告警已配置（CPU、記憶體、API 回應時間）
- [ ] 日誌收集已啟用（如 Sentry、DataDog）
- [ ] 自動化測試通過率 > 90%
- [ ] API 文件已更新至最新版本
- [ ] 容災與回滾計畫已制定

## 測試環境與 Docker (範例考量)

若專案提供 `Dockerfile`，則可依循以下方式隔離建置：
1. 確保所有的相依套件皆記錄於 `requirements.txt` 中。
2. 背景爬蟲模組由於需要常態啟動，若無設定於獨立微服務中，請確保該 Docker 環境不會被平台設定的「Idle 休眠機制」阻饒。
3. 可透過 `/health` 常綠測試端點確保程式的存活度。
