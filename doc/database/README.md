# 資料庫設計與服務整合說明

## 資料庫核心

此追蹤專案使用 **Supabase (PostgreSQL)** 作為雲端資料庫。
專案中的 Python 客戶端連線層架構於 `app.database` 之中，並使用來自 `app.config` 之安全設定。

## 核心設計理念與 Schema 角色

1.  **使用者與院所管理 (Users & Hospitals)**
    *   使用者註冊與 LINE 連動機制皆記錄於相關 Users Table 中。
    *   醫院清單（支援的爬蟲站點）建立於 Hospitals Table，以便管理狀態與停用啟用。

2.  **排程快照 (Snapshots)**
    *   為確保大量的快取資料不影響 API 回應，看診進度以及各時段爬蟲結果將以歷史快照形式寫入 Snapshots。此特性能有效供後續的 `stats.py` 資料分析使用。

3.  **掛號追蹤紀錄 (Tracking)**
    *   負責記錄單一使用者所訂閱的「特定醫師」或「特定診間」追蹤紀錄。
    *   紀錄通知狀態，例如是否已經成功以 Email 或 LINE 完成推播（防止同一階段被反覆通知）。

## 交互設計模式

所有的 Database I/O 在系統設計上大多利用 Pydantic 驗證，再送往 Supabase Data Writer (`app.services.data_writer.py`) 寫入資料庫。為了避免等待爬蟲完成，通常搭配排程（Scheduler）使用 Async 機制批次與遠端 Supabase 進行同步，確保資料流暢與效能。

## 完整 Schema 定義

### users_local (使用者帳號表)
| 欄位 | 型態 | 限制 | 說明 |
|------|------|------|------|
| id | UUID | PK | 使用者唯一識別碼 |
| username | VARCHAR(255) | UNIQUE, NOT NULL | 登入帳號 |
| email | VARCHAR(255) | UNIQUE, NOT NULL | 電子郵件 |
| hashed_password | VARCHAR(255) | NOT NULL | bcrypt 雜湊密碼 |
| line_user_id | VARCHAR(255) | UNIQUE, NULL | LINE 使用者 ID（用於 Line 通知） |
| is_admin | BOOLEAN | DEFAULT false | 是否為管理員 |
| created_at | TIMESTAMP | DEFAULT NOW() | 建立時間 |
| updated_at | TIMESTAMP | DEFAULT NOW() | 更新時間 |

**索引**：`idx_username`, `idx_email`, `idx_line_user_id`

### hospitals (醫院表)
| 欄位 | 型態 | 限制 | 說明 |
|------|------|------|------|
| id | UUID | PK | 醫院唯一識別碼 |
| hospital_code | VARCHAR(50) | UNIQUE, NOT NULL | 爬蟲識別代碼（如 "cmuh", "cmuh_hsinchu"） |
| hospital_name | VARCHAR(255) | NOT NULL | 醫院名稱 |
| location | VARCHAR(255) | NOT NULL | 醫院位置（縣市） |
| is_enabled | BOOLEAN | DEFAULT true | 是否啟用爬蟲 |
| created_at | TIMESTAMP | DEFAULT NOW() | 建立時間 |

**索引**：`idx_hospital_code`

### departments (科室表)
| 欄位 | 型態 | 限制 | 說明 |
|------|------|------|------|
| id | UUID | PK | 科室唯一識別碼 |
| hospital_id | UUID | FK → hospitals | 所屬醫院 |
| dept_code | VARCHAR(50) | NOT NULL | 科室代碼 |
| dept_name | VARCHAR(255) | NOT NULL | 科室名稱（如 "內科", "外科"） |
| created_at | TIMESTAMP | DEFAULT NOW() | 建立時間 |

**索引**：`idx_hospital_dept`, `UNIQUE(hospital_id, dept_code)`

### doctors (醫師表)
| 欄位 | 型態 | 限制 | 說明 |
|------|------|------|------|
| id | UUID | PK | 醫師唯一識別碼 |
| hospital_id | UUID | FK → hospitals | 所屬醫院 |
| dept_id | UUID | FK → departments | 所屬科室 |
| doctor_code | VARCHAR(50) | NOT NULL | 醫師代碼 |
| doctor_name | VARCHAR(255) | NOT NULL | 醫師名稱 |
| created_at | TIMESTAMP | DEFAULT NOW() | 建立時間 |

**索引**：`idx_hospital_doctor`, `idx_doctor_code`

### appointment_snapshots (門診快照表)
| 欄位 | 型態 | 限制 | 說明 |
|------|------|------|------|
| id | UUID | PK | 快照唯一識別碼 |
| doctor_id | UUID | FK → doctors | 醫師 ID |
| session_date | DATE | NOT NULL | 門診日期 |
| session_type | VARCHAR(20) | NOT NULL | 時段（"上午", "下午", "晚上"） |
| clinic_room | VARCHAR(50) | NULL | 診間房號 |
| current_number | INT | NULL | 當前叫號 |
| total_quota | INT | NULL | 總掛號數 |
| waiting_list | INT[] | NULL | 等候列表 |
| created_at | TIMESTAMP | DEFAULT NOW() | 建立時間 |
| updated_at | TIMESTAMP | DEFAULT NOW() | 更新時間 |

**索引**：`idx_snapshot_doctor_session`, `UNIQUE(doctor_id, session_date, session_type)`
**Upsert 策略**：按 (doctor_id, session_date, session_type) 衝突解決

### tracking_subscriptions (追蹤訂閱表)
| 欄位 | 型態 | 限制 | 說明 |
|------|------|------|------|
| id | UUID | PK | 訂閱唯一識別碼 |
| user_id | UUID | FK → users_local | 使用者 ID |
| doctor_id | UUID | FK → doctors | 追蹤的醫師 |
| hospital_id | UUID | FK → hospitals | 醫院 |
| session_type | VARCHAR(20) | NOT NULL | 追蹤時段（可為 NULL 表示追蹤全時段） |
| registered_number | INT | NULL | 使用者掛號號碼 |
| notify_at_20 | BOOLEAN | DEFAULT false | 當剩餘號碼 ≤ 20 時是否通知 |
| notify_at_10 | BOOLEAN | DEFAULT false | 當剩餘號碼 ≤ 10 時是否通知 |
| notify_at_5 | BOOLEAN | DEFAULT false | 當剩餘號碼 ≤ 5 時是否通知 |
| notified_20 | BOOLEAN | DEFAULT false | 是否已發送 ≤20 的通知 |
| notified_10 | BOOLEAN | DEFAULT false | 是否已發送 ≤10 的通知 |
| notified_5 | BOOLEAN | DEFAULT false | 是否已發送 ≤5 的通知 |
| enable_email | BOOLEAN | DEFAULT true | 是否啟用 Email 通知 |
| enable_line | BOOLEAN | DEFAULT true | 是否啟用 LINE 通知 |
| created_at | TIMESTAMP | DEFAULT NOW() | 建立時間 |
| updated_at | TIMESTAMP | DEFAULT NOW() | 更新時間 |

**索引**：`idx_user_subscription`, `idx_doctor_subscription`

### notification_logs (通知日誌表)
| 欄位 | 型態 | 限制 | 說明 |
|------|------|------|------|
| id | UUID | PK | 日誌唯一識別碼 |
| subscription_id | UUID | FK → tracking_subscriptions | 訂閱 ID |
| user_id | UUID | FK → users_local | 使用者 ID |
| doctor_id | UUID | FK → doctors | 醫師 ID |
| notification_type | VARCHAR(20) | NOT NULL | 通知類型（"email", "line"） |
| threshold | INT | NOT NULL | 觸發臨界值（20, 10, 或 5） |
| remaining_count | INT | NOT NULL | 通知時的剩餘號碼 |
| status | VARCHAR(20) | NOT NULL | 狀態（"sent", "failed", "skipped"） |
| error_message | TEXT | NULL | 錯誤訊息 |
| created_at | TIMESTAMP | DEFAULT NOW() | 建立時間 |

**索引**：`idx_subscription_logs`, `idx_user_logs`

## 資料關聯圖 (ER)

```
┌─────────────────┐
│   hospitals     │
├─────────────────┤
│ id (PK)         │
│ hospital_code   │
│ hospital_name   │
└────────┬────────┘
         │ 1:N
    ┌────┴──────────────────────┐
    │                           │
    ▼                           ▼
┌─────────────────┐    ┌─────────────────┐
│  departments    │    │    doctors      │
├─────────────────┤    ├─────────────────┤
│ id (PK)         │    │ id (PK)         │
│ hospital_id(FK) │    │ hospital_id(FK) │
│ dept_code       │    │ dept_id (FK)    │
└────────┬────────┘    │ doctor_name     │
         │             └────────┬────────┘
         └─────────────────────┬┘
                               │ 1:N
                        ┌──────┴──────────┐
                        │                 │
         ┌──────────────▼─────────┐ ┌────▼──────────────────┐
         │ appointment_snapshots  │ │ tracking_subscriptions│
         ├────────────────────────┤ ├───────────────────────┤
         │ id (PK)                │ │ id (PK)               │
         │ doctor_id (FK)         │ │ user_id (FK)          │
         │ session_date           │ │ doctor_id (FK)        │
         │ session_type           │ │ notify_at_20/10/5     │
         │ current_number         │ │ notified_20/10/5      │
         │ waiting_list (INT[])   │ └────────┬──────────────┘
         └────────────────────────┘         │ 1:N
                                      ┌─────▼─────────────┐
              ┌────────────────────────┤ notification_logs │
              │                        ├───────────────────┤
              │ ┌──────────────────────┤ id (PK)           │
              │ │                      │ subscription_id   │
    ┌─────────┼─┴──────────┐           │ user_id (FK)      │
    │         │            │           │ status            │
    ▼         ▼            ▼           └───────────────────┘
┌────────────────────┐
│  users_local       │
├────────────────────┤
│ id (PK)            │
│ username           │
│ email              │
│ line_user_id       │
│ is_admin           │
└────────────────────┘
```

## 資料寫入流程 (Upsert 邏輯)

### 快照寫入 (Appointment Snapshots)
```python
# 每 3 分鐘執行一次，按 (doctor_id, session_date, session_type) 衝突解決
snapshot_data = {
    'doctor_id': doctor_id,
    'session_date': session_date,
    'session_type': session_type,
    'clinic_room': clinic_room,
    'current_number': current_number,  # 只在診間開始後寫入
    'total_quota': total_quota,
    'waiting_list': waiting_list,
    'updated_at': now_utc_str()
}

response = supabase.table('appointment_snapshots').upsert(
    snapshot_data,
    on_conflict=['doctor_id', 'session_date', 'session_type']
).execute()
```

### 追蹤訂閱狀態更新 (Tracking Notifications)
```python
# 通知發送後，更新對應的 notified_XX 旗標
subscription_update = {
    'notified_20': True,  # 若已通知 ≤20
    'notified_10': True,  # 若已通知 ≤10
    'notified_5': True,   # 若已通知 ≤5
    'updated_at': now_utc_str()
}

supabase.table('tracking_subscriptions').update(
    subscription_update
).eq('id', subscription_id).execute()
```

## 查詢性能優化

### 索引策略
1. **頻繁篩選欄位**：`hospital_id`, `user_id`, `doctor_id`, `session_date`
2. **複合索引**：`(hospital_id, dept_code)`, `(doctor_id, session_date, session_type)`
3. **搜尋欄位**：`hospital_name`, `doctor_name` (若需全文搜尋，考慮 PostgreSQL Full-Text Search)

### 常見查詢最佳化

**查詢特定醫師今天的快照**
```sql
SELECT * FROM appointment_snapshots 
WHERE doctor_id = $1 AND session_date = CURRENT_DATE 
ORDER BY session_type;
```
✅ 使用複合索引 `(doctor_id, session_date)`

**查詢使用者所有追蹤訂閱及關聯醫師資訊**
```sql
SELECT ts.*, d.doctor_name, dept.dept_name, h.hospital_name 
FROM tracking_subscriptions ts
JOIN doctors d ON ts.doctor_id = d.id
JOIN departments dept ON d.dept_id = dept.id
JOIN hospitals h ON ts.hospital_id = h.id
WHERE ts.user_id = $1;
```
✅ 使用外鍵索引，確保 `ts.user_id` 有索引

**查詢通知日誌（分頁）**
```sql
SELECT * FROM notification_logs 
WHERE user_id = $1 
ORDER BY created_at DESC 
LIMIT 50 OFFSET $2;
```
✅ 使用 `idx_user_logs`，結合 `ORDER BY created_at` 需倒序索引

## 連線配置 (Supabase Python Client)

```python
from app.database import get_supabase
import asyncio

# 所有 Supabase 呼叫為同步，需用 asyncio.to_thread() 包裹
async def fetch_doctor_schedule(doctor_id: str):
    result = await asyncio.to_thread(
        lambda: get_supabase().table('doctors')
            .select('*')
            .eq('id', doctor_id)
            .execute()
    )
    return result.data[0] if result.data else None

# Batch Upsert（推薦用於大量寫入）
async def batch_insert_snapshots(snapshots: list):
    await asyncio.to_thread(
        lambda: get_supabase().table('appointment_snapshots')
            .upsert(snapshots)
            .execute()
    )
```
