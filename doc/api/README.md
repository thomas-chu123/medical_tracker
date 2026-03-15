# API 開發設計與規格說明

## 概述

系統 API 基於 FastAPI 打造，除了內建支援非同步處理之外，更透過符合 OpenAPI 的標準自動產生規格文件 (`/docs` 和 `/redoc`)。本目錄涵蓋供前端呼叫、第三方系統 Hook、及管理者維護的各項 RESTful API。

## 核心 API 路由劃分

*   **Authorization**: 負責發放以及刷新使用者 Token 的機制。
*   **Users (`/api/users`)**: 處理使用者建立、個人帳戶設定及權限管理。
*   **Hospitals (`/api/hospitals`)**: 提供列出所有支援追蹤醫療單位的科別、醫師與當日門診清單等功能。
*   **Tracking (`/api/tracking`)**: 門診進度追蹤功能設定（例如加入追蹤、更新追蹤進度、刪除追蹤項目）。
*   **Stats (`/api/stats`)**: 將目前過往看診進度進行數據彙整與統計圖表匯出。
*   **Snapshots (`/api/snapshots`)**: 提供各醫院過去門診紀錄快照查詢。
*   **Admin (`/api/admin`)**: 僅限系統管理者操作之路由，包含強制手動觸發爬蟲更新功能等。
*   **Webhooks (`/api/webhooks`)**: 提供各項第三方程式之回呼接口（例如 LINE Message API）。

## API 開發規範

1.  **資料驗證**: 所有接收與回傳資料必須使用 `app.models` 底下定義的 Pydantic Schema。
2.  **安全性 (Security)**: 需要授權管理的 API 需加入對應的 Dependency (如 JWT Token Check)。
3.  **狀態碼回傳**: 確切落實 HTTP 狀態碼：成功 (`200 OK` / `201 Created`)，或是各類特定錯誤狀態 (`400 Bad Request`, `401 Unauthorized`, `403 Forbidden`, `404 Not Found`, `500 Server Error`)。

## 詳細 API 端點清單

### 認證 (Authentication)
| 端點 | 方法 | 說明 | 認證 |
|------|------|------|------|
| `/api/auth/register` | POST | 註冊新使用者 | ❌ |
| `/api/auth/login` | POST | 使用帳號密碼登入，取得 JWT Token | ❌ |
| `/api/auth/refresh` | POST | 刷新過期的 Token | ✅ |
| `/api/auth/me` | GET | 取得目前登入使用者資訊 | ✅ |

### 使用者 (/api/users)
| 端點 | 方法 | 說明 | 認證 |
|------|------|------|------|
| `/api/users/{user_id}` | GET | 取得使用者個人資訊 | ✅ |
| `/api/users/{user_id}` | PUT | 更新使用者資訊（電子郵件、LINE ID） | ✅ |
| `/api/users/{user_id}/password` | PATCH | 修改密碼 | ✅ |
| `/api/users/{user_id}/preferences` | GET | 取得使用者通知偏好設定 | ✅ |
| `/api/users/{user_id}/preferences` | PUT | 更新通知偏好設定 | ✅ |

### 醫院 (/api/hospitals)
| 端點 | 方法 | 說明 | 認證 |
|------|------|------|------|
| `/api/hospitals` | GET | 列出所有支援的醫院 | ❌ |
| `/api/hospitals/{hospital_id}` | GET | 取得特定醫院詳細資訊 | ❌ |
| `/api/hospitals/{hospital_id}/departments` | GET | 列出醫院科室 | ❌ |
| `/api/hospitals/{hospital_id}/doctors` | GET | 列出醫院醫師及排班 | ❌ |
| `/api/hospitals/{hospital_id}/schedules` | GET | 取得今日門診時程 | ❌ |

### 追蹤 (/api/tracking)
| 端點 | 方法 | 說明 | 認證 |
|------|------|------|------|
| `/api/tracking/subscriptions` | GET | 取得目前使用者的所有追蹤訂閱 | ✅ |
| `/api/tracking/subscriptions` | POST | 建立新的追蹤訂閱 | ✅ |
| `/api/tracking/subscriptions/{sub_id}` | GET | 取得特定追蹤訂閱詳情 | ✅ |
| `/api/tracking/subscriptions/{sub_id}` | PUT | 更新追蹤訂閱設定 | ✅ |
| `/api/tracking/subscriptions/{sub_id}` | DELETE | 刪除追蹤訂閱 | ✅ |
| `/api/tracking/status/{doctor_id}` | GET | 查詢特定醫師目前門診進度 | ✅ |

### 統計 (/api/stats)
| 端點 | 方法 | 說明 | 認證 |
|------|------|------|------|
| `/api/stats/summary` | GET | 取得整體統計摘要（今日、本週、本月） | ✅ |
| `/api/stats/crowd-analysis` | GET | 人潮分析：各時段平均等待人數 | ✅ |
| `/api/stats/doctor/{doctor_id}/history` | GET | 取得醫師看診歷史紀錄 | ✅ |

### 快照 (/api/snapshots)
| 端點 | 方法 | 說明 | 認證 |
|------|------|------|------|
| `/api/snapshots/history` | GET | 查詢門診歷史快照（可按日期篩選） | ✅ |
| `/api/snapshots/{snapshot_id}` | GET | 取得特定快照詳情 | ✅ |

### 管理者 (/api/admin)
| 端點 | 方法 | 說明 | 認證 |
|------|------|------|------|
| `/api/admin/scrape-now` | POST | 立即觸發爬蟲更新所有醫院資料 | ✅ 管理員 |
| `/api/admin/users` | GET | 列出所有註冊使用者（分頁） | ✅ 管理員 |
| `/api/admin/users/{user_id}` | PATCH | 更新使用者權限 | ✅ 管理員 |
| `/api/admin/notifications/logs` | GET | 查看通知發送日誌 | ✅ 管理員 |

### Webhooks (/api/webhooks)
| 端點 | 方法 | 說明 | 認證 |
|------|------|------|------|
| `/api/webhooks/line/message` | POST | LINE Message API 回呼接口 | ✅ LINE簽名驗證 |

## 認證流程

### JWT Token 認證機制
1. **登入** (`POST /api/auth/login`，發送帳號密碼)
   - 回傳：`access_token`、`token_type`、`expires_in`
2. **使用 Token** (後續 API 呼叫於 `Authorization: Bearer <access_token>` Header)
3. **Token 過期** (通常 24 小時)
   - 呼叫 `POST /api/auth/refresh` 取得新 Token

### 常見認證錯誤
| 狀態碼 | 錯誤訊息 | 解決方式 |
|--------|--------|--------|
| 401 | `Unauthorized: Invalid token` | Token 已過期或格式錯誤，使用 refresh endpoint |
| 401 | `Unauthorized: Missing token` | 缺少 Authorization Header |
| 403 | `Forbidden: Insufficient permissions` | 該帳號非管理員，無法存取此路由 |

## API 使用範例

### 登入範例 (cURL)
```bash
curl -X POST "http://localhost:8000/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"user@example.com","password":"password123"}'
```
回應：
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 86400
}
```

### 查詢醫院範例 (Python)
```python
import httpx
import asyncio

async def get_hospitals():
    async with httpx.AsyncClient() as client:
        response = await client.get("http://localhost:8000/api/hospitals")
        return response.json()

hospitals = asyncio.run(get_hospitals())
print(hospitals)
```

### 建立追蹤訂閱 (JavaScript)
```javascript
const token = localStorage.getItem('access_token');
const response = await fetch('/api/tracking/subscriptions', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`
  },
  body: JSON.stringify({
    doctor_id: 'doc_12345',
    hospital_id: 'cmuh',
    notify_at_20: true,
    notify_at_10: true,
    notify_at_5: true,
    enable_email: true,
    enable_line: true
  })
});
const data = await response.json();
```

## 錯誤回應格式

所有錯誤回應皆採用統一格式：
```json
{
  "detail": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid input data",
    "errors": [
      {
        "field": "email",
        "message": "Invalid email format"
      }
    ]
  }
}
```

## OpenAPI 規格文件

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

本系統自動從代碼生成 OpenAPI 規格，無需手動維護文件。
