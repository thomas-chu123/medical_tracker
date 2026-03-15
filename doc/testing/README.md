# 系統測試指南

為了確保醫療門診爬蟲系統的可靠度，專案提供基礎的測試方針。

## 測試環境分類

本專案應專注於三類測試環境：
1. **API Endpoints 測試**: 使用 FastAPI 內建的 `TestClient`。
2. **Scraper 單元測試**: 在不發送實際的 Requests （或者透過建立 Mock Server/響應檔），檢驗 XPath 或 Regex 之解析規則是否符合預期。
3. **資料整合測試**: 包含測試資料能否被準確寫入，並確認 Supabase 處理端正常。

## 如何新增測試

我們建議在開發完任何 Endpoint 後，將相對應的預期結果加上斷言 (Assertion)。
未來於 CI/CD Pipeline（例如 GitHub Actions 或 GitLab CI）中，一併透過設定檔進行全面測試。

另外請確認測試環境使用的資料庫不可為 Production，以避免污染既有客戶資料。

## 詳細測試分類說明

### 1. 單元測試 (Unit Tests)
**目標**：測試單一函式或方法的邏輯正確性

**位置**：`tests/` 目錄
**執行方式**：
```bash
pytest tests/ -m unit -v
```

**範例**：
```python
# tests/scraper/test_calculate_remaining_count.py
from app.scrapers.cmuh import CMUHScraper

def test_calculate_remaining_with_waiting_list():
    """測試計算剩餘號碼邏輯"""
    waiting_list = [101, 102, 103, 104, 105]
    current_number = 100
    
    result = CMUHScraper.calculate_remaining_count(
        current_number, waiting_list, total_quota=150
    )
    assert result == 5  # 5 人在隊列中
```

### 2. 整合測試 (Integration Tests)
**目標**：測試多個元件協作是否正常

**位置**：`tests/` 目錄（帶 `@pytest.mark.integration`）
**執行方式**：
```bash
pytest tests/ -m integration -v
```

**範例**：
```python
# tests/api/test_api_tracking_integration.py
@pytest.mark.integration
async def test_create_tracking_writes_to_supabase(mock_supabase):
    """測試建立追蹤訂閱是否寫入資料庫"""
    response = client.post(
        "/api/tracking/subscriptions",
        json={
            "doctor_id": "doc_123",
            "notify_at_20": True
        },
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 201
    
    # 驗證資料庫被呼叫
    mock_supabase.table.assert_called_with('tracking_subscriptions')
```

### 3. 端對端測試 (E2E Tests)
**目標**：測試完整的使用者流程

**位置**：`tests/e2e/`
**執行方式**：
```bash
pytest tests/e2e/test_ui_selenium.py -v  # 需啟動伺服器
```

## 測試清單

### API 測試清單
- [ ] 認證 (Authentication)
  - [ ] 註冊新帳號成功
  - [ ] 登入有效憑證
  - [ ] 登入無效憑證應失敗
  - [ ] 過期 Token 應刷新
  - [ ] 缺少 Token 應返回 401

- [ ] 醫院/科室查詢
  - [ ] 列出所有醫院
  - [ ] 查詢特定醫院詳情
  - [ ] 按科室篩選
  - [ ] 無效醫院 ID 應返回 404

- [ ] 追蹤管理
  - [ ] 建立新追蹤訂閱
  - [ ] 更新追蹤設定
  - [ ] 刪除追蹤訂閱
  - [ ] 查詢使用者訂閱清單
  - [ ] 未認證使用者無法建立訂閱

- [ ] 統計資料
  - [ ] 取得今日統計摘要
  - [ ] 人潮分析資料正確
  - [ ] 醫師歷史紀錄可查詢

### 爬蟲測試清單
- [ ] 科室解析
  - [ ] 科室代碼正確提取
  - [ ] 科室名稱無誤
  
- [ ] 排班解析
  - [ ] 醫師名稱正確解析
  - [ ] 時段資訊完整
  - [ ] 掛號額度準確
  
- [ ] 診間進度解析
  - [ ] 當前叫號準確
  - [ ] 等候列表正確
  - [ ] 異常狀態處理（無診間、已結束等）

### 通知測試清單
- [ ] Email 通知
  - [ ] 門檻觸發時發送
  - [ ] 郵件格式正確
  - [ ] SMTP 連線失敗時不拋例外
  
- [ ] LINE 通知
  - [ ] 訊息格式正確
  - [ ] LINE API 連線失敗時重試
  - [ ] 避免重複通知

## Mock 資料範例

### Mock 醫院資料
```python
MOCK_HOSPITAL = {
    'id': 'hospital_cmuh',
    'hospital_code': 'cmuh',
    'hospital_name': '中國醫藥大學附設醫院',
    'location': '台中市',
    'is_enabled': True
}

MOCK_DOCTOR_SCHEDULE = [
    {
        'id': 'doc_001',
        'doctor_name': '李醫師',
        'dept_code': 'IM',
        'dept_name': '內科',
        'morning': {'quota': 20},
        'afternoon': {'quota': 15},
        'evening': None
    }
]

MOCK_CLINIC_PROGRESS = {
    'clinic_room': 'A101',
    'current_number': 50,
    'total_quota': 80,
    'waiting_list': [51, 52, 53, 54, 55],
    'session_start': '08:30',
    'session_end': '16:45'
}
```

### Mock 使用者與訂閱
```python
MOCK_USER = {
    'id': 'user_123',
    'username': 'testuser@example.com',
    'email': 'testuser@example.com',
    'line_user_id': 'U1234567890abcdef',
    'is_admin': False
}

MOCK_SUBSCRIPTION = {
    'id': 'sub_001',
    'user_id': 'user_123',
    'doctor_id': 'doc_001',
    'registered_number': 50,
    'notify_at_20': True,
    'notify_at_10': True,
    'notify_at_5': True,
    'notified_20': False,
    'notified_10': False,
    'notified_5': False,
    'enable_email': True,
    'enable_line': True
}
```

## 覆蓋率目標

| 模組 | 目標 | 說明 |
|------|------|------|
| `app/api/` | 85% | API 路由必須有充分測試 |
| `app/services/` | 80% | 商業邏輯應高度測試 |
| `app/scrapers/` | 75% | 爬蟲解析規則應測試 |
| `app/core/` | 70% | 輔助模組可接受較低覆蓋率 |
| **整體** | **80%** | 目標總覆蓋率 |

**查看覆蓋率**：
```bash
pytest tests/ --cov=app --cov-report=html
# 會生成 htmlcov/index.html
```

## CI/CD 工作流配置 (GitHub Actions)

**檔案**：`.github/workflows/test.yml`
```yaml
name: Tests

on:
  push:
    branches: [main, dev]
  pull_request:
    branches: [main, dev]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
      
      - name: Run tests
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
        run: |
          pytest tests/ --cov=app --cov-report=xml
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

## 測試最佳實踐

### ✅ 好的測試
```python
def test_calculate_eta_for_evening_session():
    """
    測試晚上時段跨越午夜的 ETA 計算。
    邊界案例：診間 18:00 開始，02:00 結束，跨越午夜。
    """
    session_date = "2025-01-15"
    current_number = 100
    target_number = 110
    waiting_list = [101, 102, ..., 110]
    
    eta = calculate_eta(
        session_date=session_date,
        session_type="晚上",
        current_number=current_number,
        registered_count=150,
        waiting_list=waiting_list,
        target_number=target_number
    )
    
    # 應返回晚上時段內的時間
    assert eta is not None
    assert "01:30" <= eta <= "02:00"  # 實際邊界檢查
```

### ❌ 不好的測試
```python
def test_eta():
    """太籠統，無法清楚表達測試意圖"""
    result = calculate_eta("2025-01-15", "晚上", 100, 150, [101, 102], 110)
    assert result is not None  # 斷言太寬鬆
```

## 測試執行命令速查

| 命令 | 說明 |
|------|------|
| `pytest tests/` | 執行所有測試 |
| `pytest tests/ -v` | 詳細模式（顯示各測試名稱） |
| `pytest tests/ -s` | 顯示 print 輸出 |
| `pytest tests/api/` | 只執行 API 測試 |
| `pytest tests/ -k "tracking"` | 執行名稱含 "tracking" 的測試 |
| `pytest tests/ --tb=short` | 簡化錯誤堆疊追蹤 |
| `pytest tests/ --cov=app` | 顯示覆蓋率 |
| `pytest tests/ -m integration` | 只執行整合測試 |
| `pytest tests/ -x` | 首次失敗時停止 |
