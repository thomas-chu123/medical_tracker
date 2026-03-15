# 開發指南

## 專案設定

在此專案中請遵循我們對於程式撰寫、管理以及工具鏈的要求，以確保系統架構可長久維護與運作。

### 依賴控管

我們主要採用標準的 `requirements.txt` 以保留專案所需套件之鎖定，當新增專案模組時，請依照下列工具準備：

1. FastAPI 相關網路框架
2. SQLAlchemy / Supabase client (資料庫層級)
3. BeautifulSoup4 或類似解析模組 (Crawler 模組專用)
4. APScheduler (排程模組使用)
5. Pydantic / Pydantic Settings (配置管理與驗證)

## 開發環境規範

1.  **版控訊息格式**: `[元件/情境] 修改/新增事項` (本專案後續更新需採用全英文 Commit 訊息以維護日誌的一致性)
2.  **型別提示**(Type Hints): 強烈建議 Python 代碼中加入完整型別，以利用 IDE 的分析功能。
3.  **單一職責**: API Controller 與 Service 的邏輯必須拆解；所有爬蟲相關業務請統一集中管理於 `app.scrapers`。

## 如何啟動測試開發環境

在進入開發準備工作前，請參閱 `.env.example` 確保本地環境有設定正確。
由於涉及許多非同步與遠端環境串接，開發請隨時關注 `app/core/logger.py` 下的相關日誌輸出是否異常。

## 本地開發環境設置

### 步驟 1：複製專案並建立虛擬環境
```bash
# 複製專案
git clone https://github.com/your-org/medial_help.git
cd medial_help

# 建立虛擬環境
python3 -m venv venv
source venv/bin/activate  # Unix/Mac
# 或 venv\Scripts\activate  # Windows

# 升級 pip
pip install --upgrade pip
```

### 步驟 2：安裝依賴
```bash
pip install -r requirements.txt
```

### 步驟 3：環境設定
```bash
# 複製環境變數範例
cp .env.example .env

# 編輯 .env，填入實際的 Supabase、JWT、Email、LINE 設定
nano .env
```

### 步驟 4：啟動開發伺服器
```bash
# 啟動 FastAPI 開發伺服器（支援自動重載）
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 訪問 API 文件
# - Swagger UI: http://localhost:8000/docs
# - ReDoc: http://localhost:8000/redoc
```

### 步驟 5：執行測試
```bash
# 執行所有單元測試
pytest tests/ --ignore=tests/test_ui_selenium.py --ignore=tests/test_ui_e2e_minimal.py -v

# 執行特定測試檔
pytest tests/api/test_api.py -v

# 執行測試並生成覆蓋率報告
pytest tests/ --cov=app --cov-report=html
```

## Git 工作流程

### 分支策略
- **`main`**：生產環境分支，所有 commit 需通過 Code Review
- **`dev`**：開發分支，多人協作的整合分支
- **`feature/<功能名>`**：功能分支，如 `feature/add-notification-logs`
- **`bugfix/<bug名>`**：修復分支，如 `bugfix/fix-eta-calculation`

### 開發流程

1. **建立功能分支**
```bash
git checkout dev
git pull origin dev
git checkout -b feature/your-feature-name
```

2. **提交變更**
```bash
# 提交訊息格式：<type>(<scope>): <subject>
# 範例：feat(scheduler): add new hospital scraper
git commit -m "feat(scheduler): add new hospital scraper"
```

**Commit 類型**：
- `feat`: 新功能
- `fix`: 修復錯誤
- `docs`: 文件變更
- `style`: 格式調整（不影響代碼邏輯）
- `refactor`: 程式碼重構
- `test`: 測試相關
- `chore`: 配置/依賴更新

3. **推送並建立 Pull Request**
```bash
git push origin feature/your-feature-name
```
在 GitHub 上建立 PR，目標分支為 `dev`

4. **Code Review**
PR 應包含：
- [ ] 清晰的修改說明
- [ ] 相關 Issue 連結
- [ ] 通過所有單元測試
- [ ] 未減少既有測試覆蓋率
- [ ] 至少一位團隊成員的 Approve

5. **合併與清理**
```bash
# PR 被 merge 後
git checkout dev
git pull origin dev
git branch -d feature/your-feature-name
```

## IDE 設置建議

### VSCode 設定（推薦）

**安裝擴充**：
- `Python` (Microsoft)
- `Pylance` (Microsoft) - 進階型別檢查
- `Black Formatter` - 程式碼格式化
- `Flake8` - Linting（選用）
- `REST Client` - API 測試
- `Thunder Client` 或 `REST Client` - 免費 Postman 替代

**VSCode settings.json**
```json
{
  "[python]": {
    "editor.defaultFormatter": "ms-python.black-formatter",
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
      "source.organizeImports": true
    }
  },
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": false,
  "python.linting.flake8Enabled": true,
  "python.analysis.typeCheckingMode": "basic",
  "python.linting.flake8Args": [
    "--max-line-length=100",
    "--ignore=E203,W503"
  ]
}
```

### PyCharm 設定（專業版）

1. **設定 Python 直譯器**：Settings → Project → Python Interpreter → 選擇 `venv`
2. **啟用型別檢查**：Settings → Editor → Inspections → 啟用 Type Hints
3. **設定 Commit 訊息範本**：Settings → Version Control → Commit → Commit Message

## 常見開發命令速查表

| 命令 | 說明 |
|------|------|
| `uvicorn app.main:app --reload` | 啟動開發伺服器 |
| `pytest tests/` | 執行所有測試 |
| `pytest tests/api/test_api.py::test_health_check` | 執行特定測試 |
| `pytest tests/ -v -s` | 執行測試並顯示詳細輸出 |
| `black app/` | 格式化 app 目錄下所有 Python 檔 |
| `flake8 app/` | 檢查程式碼風格 |
| `python -m app.scheduler` | 手動啟動排程模組（用於測試） |

## 編碼最佳實踐

### 型別提示範例
```python
from typing import Optional, List
from datetime import datetime

async def fetch_doctors(hospital_id: str, limit: int = 50) -> List[dict]:
    """
    取得醫院醫師清單。
    
    Args:
        hospital_id: 醫院 ID
        limit: 返回數量限制
    
    Returns:
        醫師資訊字典清單
    """
    # 實作...
    pass

def calculate_eta(
    current_number: Optional[int],
    total_ahead: int,
    minutes_per_patient: int = 5
) -> Optional[datetime]:
    """計算預估看診時間"""
    if current_number is None:
        return None
    return datetime.now() + timedelta(minutes=total_ahead * minutes_per_patient)
```

### 非同步寫入最佳實踐
```python
import asyncio

# ✅ 正確：使用 asyncio.to_thread 包裹 Supabase 呼叫
async def get_doctor_info(doctor_id: str):
    result = await asyncio.to_thread(
        lambda: supabase.table('doctors')
            .select('*')
            .eq('id', doctor_id)
            .execute()
    )
    return result.data[0] if result.data else None

# ❌ 錯誤：直接呼叫 sync 函式，會阻塞事件迴圈
# result = supabase.table('doctors').select('*').execute()
```

### 日誌記錄範例
```python
from app.core.logger import logger

logger.info(f"開始爬取醫院 {hospital_name} 的資料")
logger.warning(f"醫師 {doctor_name} 無排班資訊，跳過")
logger.error(f"連線 Supabase 失敗：{error_message}")
```

## 常見開發問題

| 問題 | 解決方式 |
|------|--------|
| **ModuleNotFoundError: No module named 'app'** | 確認在專案根目錄執行命令；確認虛擬環境已激活 |
| **Pydantic validation error** | 檢查 API 請求體是否符合 Schema；使用 `curl -v` 或 Swagger UI 測試 |
| **Supabase 連線逾時** | 檢查 `SUPABASE_URL` 是否正確；檢查網路連線；嘗試增加超時時間 |
| **非同步任務卡住** | 檢查是否有 blocking I/O 直接呼叫；使用 `asyncio.to_thread()` 包裹 sync 函式 |
| **爬蟲解析失敗** | 目標網站可能已更新 HTML 結構；檢查 XPath/CSS Selector；更新爬蟲邏輯 |
