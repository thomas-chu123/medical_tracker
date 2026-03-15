# VS Code、GitHub Copilot、Copilot CLI 設定位置對應

本文檔說明開發工具的設定位置及其用途。

## 路徑對應表

| 路徑 | 應用 | 用途 | 文件類型 |
|------|------|------|---------|
| `~/Library/Application Support/Code/User/` | **VS Code** | VS Code 本身的用戶設定 | `settings.json`, `keybindings.json`, `snippets/` |
| `~/.vscode/` | **VS Code 擴展** | 安裝的擴展和工作區級設定 | `extensions/`, `settings.json` |
| `~/.config/github-copilot/` | **GitHub Copilot CLI** | Copilot CLI 的認證和設定 | `hosts.json`, `token` 等 |
| `~/.copilot/` | **GitHub Copilot（已棄用）** | 舊版本的 Copilot 設定目錄 | 不建議使用 |

---

## 詳細說明

### 1. VS Code 主設定目錄
**路徑**：`~/Library/Application Support/Code/User/`

**用途**：存儲 VS Code 的全局用戶設定

**主要文件**：
- `settings.json` — 編輯器設定（字體、主題、語言等）
- `keybindings.json` — 自定義快捷鍵
- `snippets/` — 代碼片段目錄
- `locale.json` — 語言設定

**訪問方式**：
```bash
# 打開設定文件
open ~/Library/Application\ Support/Code/User/settings.json

# 在 VS Code 中
快捷鍵：Cmd + ,
```

---

### 2. VS Code 擴展目錄
**路徑**：`~/.vscode/`

**結構**：
```
~/.vscode/
├── extensions/              # 已安裝的擴展
│   ├── publisher.ext-1.0.0/
│   ├── publisher.ext-2.0.0/
│   └── ...
├── settings.json           # 工作區級設定（可選）
└── launch.json            # 調試配置（可選）
```

**用途**：
- 存儲已安裝的 VS Code 擴展
- 可選的工作區級設定（會覆蓋用戶全局設定）

**注意**：工作區級設定應放在 `<project>/.vscode/settings.json`，而非 `~/.vscode/`

---

### 3. GitHub Copilot CLI 設定
**路徑**：`~/.config/github-copilot/`

**用途**：存儲 Copilot CLI 的認證令牌和配置

**主要文件**：
- `hosts.json` — GitHub 主機配置
- `token` — 認證令牌

**CLI 命令**：
```bash
# 登錄 GitHub Copilot CLI
gh copilot auth login

# 驗證認證狀態
gh copilot auth status

# 查詢建議
copilot suggest "your query"
```

**與 VS Code 的關係**：
- Copilot CLI 是命令行工具
- VS Code Copilot 擴展使用單獨的認證機制

---

### 4. GitHub Copilot（已棄用）
**路徑**：`~/.copilot/`

**狀態**：⚠️ **已棄用**，不建議使用

**說明**：
- 這是舊版 GitHub Copilot 的設定目錄
- 已被新的 VS Code 擴展和 Copilot CLI 取代
- 如存在可以安全刪除

---

## Model Context Protocol (MCP) 設定

MCP 伺服器的設定位置取決於使用方式：

### VS Code 中的 MCP 設定

**路徑**：
```
~/Library/Application Support/Code/User/globalStorage/
    copilot-settings/<MCP-Server-Name>/
```

或通過 VS Code 設定文件：
```json
// ~/Library/Application Support/Code/User/settings.json
{
  "github.copilot.advanced": {
    "mcp_server": {
      "your-server-name": {
        "command": "path/to/server",
        "args": ["--option"]
      }
    }
  }
}
```

### Copilot CLI 中的 MCP 設定

**配置文件**：
```bash
~/.config/github-copilot/config.yaml
```

**示例**：
```yaml
mcp_servers:
  my-server:
    command: /path/to/server
    args: []
    env:
      VAR_NAME: value
```

### 項目級別的 MCP 設定

**推薦位置**：
```bash
<project>/.copilot/mcp-servers.yaml
# 或
<project>/.github/copilot.yaml
```

**示例**（`.copilot/mcp-servers.yaml`）：
```yaml
# MCP 伺服器配置
servers:
  project-tools:
    command: python
    args:
      - -m
      - app.mcp_server
    env:
      PYTHONPATH: .
```

---

## 快速參考

| 任務 | 位置 | 方法 |
|------|------|------|
| 修改 VS Code 主題 | `~/Library/Application Support/Code/User/settings.json` | Cmd + , 打開設定 GUI |
| 自定義快捷鍵 | `~/Library/Application Support/Code/User/keybindings.json` | Cmd + K, Cmd + S 打開快捷鍵編輯器 |
| 登錄 Copilot CLI | `~/.config/github-copilot/` | 運行 `gh copilot auth login` |
| 配置 MCP 伺服器（全局） | `~/.config/github-copilot/config.yaml` | 編輯 YAML 文件 |
| 配置 MCP 伺服器（項目級） | `<project>/.copilot/mcp-servers.yaml` | 編輯項目中的 YAML 文件 |
| 查看已安裝擴展 | `~/.vscode/extensions/` | `ls -la ~/.vscode/extensions/` |

---

## 環境變量

在任何配置中使用環境變量時，使用以下格式：

```bash
# 在 config.yaml 或 settings.json 中
$HOME              # 用戶主目錄
$PYTHONPATH        # Python 模塊路徑
$PATH              # 系統路徑
```

---

## 故障排查

### Copilot 認證問題
```bash
# 檢查認證狀態
gh auth status
gh copilot auth status

# 重新登錄
gh auth login
gh copilot auth login
```

### 清除所有設定（謹慎操作）
```bash
# 備份後再清除
cp -r ~/.config/github-copilot ~/.config/github-copilot.backup
rm -rf ~/.config/github-copilot

# 重新初始化
gh copilot auth login
```

### VS Code 擴展問題
```bash
# 列出所有擴展
code --list-extensions

# 卸載特定擴展
code --uninstall-extension publisher.extension

# 禁用擴展
# 在 VS Code 中：Cmd + Shift + X → 搜索擴展 → 點擊齒輪 → 禁用
```

---

## 相關文檔

- [VS Code 用戶指南](https://code.visualstudio.com/docs)
- [GitHub Copilot CLI 文檔](https://docs.github.com/en/copilot/using-github-copilot/copilot-cli)
- [Model Context Protocol 文檔](https://modelcontextprotocol.io/)

